"""
LLMOps 监控 API — 借鉴 Dify LLMOps 设计

提供: API 调用统计 / 延迟追踪 / Token 估算 / 工具调用计数
"""

import time
import logging
from collections import defaultdict
from datetime import datetime
from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# ====== 内存统计 (生产可换 Redis/Prometheus) ======

_stats = {
    "total_requests": 0,
    "total_success": 0,
    "total_errors": 0,
    "total_latency_ms": 0,
    "total_tokens": 0,
    "by_endpoint": defaultdict(lambda: {"count": 0, "total_ms": 0, "errors": 0}),
    "by_hour": defaultdict(int),
    "tool_calls": defaultdict(int),
    "ratings": [],  # [(score, comment), ...]
    "recent_requests": [],  # 最近 50 条
    "start_time": datetime.now().isoformat(),
}


async def track_request(request: Request, call_next):
    """FastAPI 中间件: 记录每个请求的统计信息"""
    start = time.time()
    response = None
    error = False
    try:
        response = await call_next(request)
        return response
    except Exception:
        error = True
        raise
    finally:
        elapsed_ms = (time.time() - start) * 1000
        path = request.url.path
        method = request.method

        _stats["total_requests"] += 1
        _stats["total_latency_ms"] += elapsed_ms

        ep = _stats["by_endpoint"][f"{method} {path}"]
        ep["count"] += 1
        ep["total_ms"] += elapsed_ms
        if error or (response and response.status_code >= 400):
            _stats["total_errors"] += 1
            ep["errors"] += 1
        else:
            _stats["total_success"] += 1

        # 按小时统计
        hour_key = datetime.now().strftime("%H:00")
        _stats["by_hour"][hour_key] += 1

        # 最近请求
        _stats["recent_requests"].append({
            "time": datetime.now().isoformat(),
            "method": method,
            "path": path,
            "status": response.status_code if response else 500,
            "latency_ms": round(elapsed_ms, 1),
        })
        if len(_stats["recent_requests"]) > 50:
            _stats["recent_requests"] = _stats["recent_requests"][-50:]


# ====== 公开统计 API ======


@router.get("/stats", tags=["监控"])
async def get_stats():
    """LLMOps 总览统计"""
    total = _stats["total_requests"]
    avg_latency = round(_stats["total_latency_ms"] / max(total, 1), 1)
    error_rate = round(_stats["total_errors"] / max(total, 1) * 100, 1)

    # Top 端点 (按调用量)
    top_endpoints = sorted(
        [{"endpoint": k, **v, "avg_ms": round(v["total_ms"] / max(v["count"], 1), 1)}
         for k, v in _stats["by_endpoint"].items()],
        key=lambda x: x["count"], reverse=True,
    )[:10]

    # Top 工具
    top_tools = sorted(
        [{"tool": k, "calls": v} for k, v in _stats["tool_calls"].items()],
        key=lambda x: x["calls"], reverse=True,
    )

    # 按小时分布
    hourly = [{"hour": k, "count": v} for k, v in sorted(_stats["by_hour"].items())]

    # 评分统计
    ratings = _stats["ratings"]
    avg_rating = round(sum(r[0] for r in ratings) / max(len(ratings), 1), 1) if ratings else None

    return {
        "overview": {
            "total_requests": total,
            "success": _stats["total_success"],
            "errors": _stats["total_errors"],
            "error_rate_pct": error_rate,
            "avg_latency_ms": avg_latency,
            "total_tokens": _stats["total_tokens"],
        },
        "avg_rating": avg_rating,
        "rating_count": len(ratings),
        "top_endpoints": top_endpoints,
        "top_tools": top_tools,
        "hourly_requests": hourly[-24:],
        "recent_requests": _stats["recent_requests"][-20:],
        "uptime_since": _stats["start_time"],
    }


@router.get("/stats/dashboard", tags=["监控"])
async def dashboard_summary():
    """监控面板 — 简化摘要"""
    total = max(_stats["total_requests"], 1)
    ratings = _stats["ratings"]
    return {
        "requests_total": _stats["total_requests"],
        "success_rate": round(_stats["total_success"] / total * 100, 1),
        "avg_latency_ms": round(_stats["total_latency_ms"] / total, 1),
        "errors_today": _stats["total_errors"],
        "avg_rating": round(sum(r[0] for r in ratings) / max(len(ratings), 1), 1) if ratings else None,
        "tools_used": len(_stats["tool_calls"]),
    }


# ====== 对话评分 ======

class RatingRequest(BaseModel):
    session_id: str
    score: int  # 1-5
    comment: str = ""


@router.post("/chat/rate", tags=["对话"])
async def rate_conversation(req: RatingRequest):
    """对话评分 (1-5 星)"""
    if not (1 <= req.score <= 5):
        from fastapi import HTTPException
        raise HTTPException(400, "评分需在 1-5 之间")

    _stats["ratings"].append((req.score, req.comment))
    logger.info(f"对话评分: {req.score}⭐ | {req.comment[:50] if req.comment else ''}")
    return {"status": "ok", "message": "感谢您的反馈!"}


# ====== 工具调用追踪 (供内部使用) ======

def track_tool_call(tool_name: str):
    """内部函数: 记录一次工具调用"""
    _stats["tool_calls"][tool_name] += 1


def track_token_usage(count: int):
    """内部函数: 记录 token 消耗"""
    _stats["total_tokens"] += count
