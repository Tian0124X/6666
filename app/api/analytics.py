"""
业务分析 API — 用户行为 / 知识库 / 性能 / 趋势

2026: 从 API 请求计数升级为真实业务指标
"""

import json
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import APIRouter, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


# ====== 事件追踪 (内部调用) ======

class AnalyticsTracker:
    """轻量埋点 — 不阻塞请求，fire-and-forget 写 DB + 内存"""

    def __init__(self):
        self._buffer: list = []  # 内存缓冲
        self._daily_active_users: set = set()
        self._hourly_activity: dict = defaultdict(int)

    def track(self, event_type: str, user_id: str = "anonymous", session_id: str = "", data: dict | None = None):
        """记录事件 (同步轻量, 异步持久化)"""
        import asyncio
        hour = datetime.now().strftime("%H:00")
        self._hourly_activity[hour] += 1
        if user_id and user_id != "anonymous":
            self._daily_active_users.add(user_id)

        # 异步写 DB
        asyncio.create_task(self._persist(event_type, user_id, session_id, data))

    async def _persist(self, event_type: str, user_id: str, session_id: str, data: dict | None):
        try:
            from app.models.database import get_session, AnalyticsEvent
            db = get_session()
            if db is None:
                return
            evt = AnalyticsEvent(
                event_type=event_type,
                user_id=user_id,
                session_id=session_id,
                data_json=data,
            )
            db.add(evt)
            db.commit()
            db.close()
        except Exception:
            pass  # 静默失败，不影响主流程

    def get_stats(self) -> dict:
        """获取当前内存统计 (实时)"""
        return {
            "dau": len(self._daily_active_users),
            "hourly_activity": dict(sorted(self._hourly_activity.items())[-24:]),
            "total_events": sum(self._hourly_activity.values()),
        }


_tracker = AnalyticsTracker()


def track_event(event_type: str, user_id: str = "anonymous", session_id: str = "", data: dict | None = None):
    """公开埋点函数 — 供其他模块调用"""
    _tracker.track(event_type, user_id, session_id, data)


# ====== API 端点 ======


@router.get("/analytics/overview", tags=["分析"])
async def analytics_overview():
    """业务总览 KPI"""
    from app.api.monitoring import _store
    mon = _store.get_dashboard()

    # 从 DB 获取历史数据
    db_stats = await _get_db_stats()

    return {
        "today": {
            "dau": _tracker.get_stats()["dau"],
            "requests": mon["requests_total"],
            "success_rate": mon["success_rate"],
            "avg_latency_ms": mon["avg_latency_ms"],
            "avg_rating": mon["avg_rating"],
            "errors": mon["errors_today"],
        },
        "knowledge": db_stats.get("knowledge", {}),
        "tools": db_stats.get("tools", {}),
        "performance": db_stats.get("performance", {}),
    }


@router.get("/analytics/trends", tags=["分析"])
async def analytics_trends(days: int = Query(default=7, ge=1, le=90)):
    """趋势数据 — 对话量/成功率/延迟按天"""
    from app.models.database import get_session, AnalyticsEvent
    from sqlalchemy import func

    db = get_session()
    if db is None:
        return {"trends": [], "message": "数据库不可用"}

    try:
        since = datetime.utcnow() - timedelta(days=days)
        rows = (
            db.query(
                func.date(AnalyticsEvent.created_at).label("date"),
                AnalyticsEvent.event_type,
                func.count().label("count"),
            )
            .filter(AnalyticsEvent.created_at >= since)
            .group_by("date", AnalyticsEvent.event_type)
            .order_by("date")
            .all()
        )

        # 按日期聚合
        trends: dict = {}
        for r in rows:
            d = str(r.date)
            if d not in trends:
                trends[d] = {"date": d, "total": 0}
            trends[d][r.event_type] = r.count
            trends[d]["total"] += r.count

        return {"trends": list(trends.values()), "days": days}

    except Exception as e:
        return {"trends": [], "message": str(e)}
    finally:
        db.close()


@router.get("/analytics/knowledge", tags=["分析"])
async def analytics_knowledge():
    """知识库使用统计"""
    from app.api.monitoring import _store

    return {
        "rag_queries_today": _store.tool_calls.get("knowledge_search", 0),
        "top_tools": dict(sorted(_store.tool_calls.items(), key=lambda x: x[1], reverse=True)[:5]),
        "cache_hit_rate": await _get_cache_stats(),
    }


@router.get("/analytics/performance", tags=["分析"])
async def analytics_performance():
    """性能分布 — P50/P95/P99"""
    from app.api.monitoring import _store
    recent = _store.recent_requests

    if not recent:
        return {"p50": 0, "p95": 0, "p99": 0, "samples": 0}

    latencies = sorted([r.get("latency_ms", 0) for r in recent])
    n = len(latencies)

    def percentile(pct):
        idx = int(n * pct / 100)
        return latencies[min(idx, n - 1)] if n > 0 else 0

    return {
        "p50": round(percentile(50), 1),
        "p95": round(percentile(95), 1),
        "p99": round(percentile(99), 1),
        "min": round(latencies[0], 1) if n > 0 else 0,
        "max": round(latencies[-1], 1) if n > 0 else 0,
        "samples": n,
    }


# ====== 内部辅助 ======

async def _get_db_stats() -> dict:
    """从 DB 获取聚合统计"""
    try:
        from app.models.database import get_session, AnalyticsEvent, EvalRecord
        from sqlalchemy import func

        db = get_session()
        if db is None:
            return {}

        today = datetime.utcnow().date()
        result = {}

        # 知识库统计
        kb = (
            db.query(AnalyticsEvent.event_type, func.count().label("c"))
            .filter(AnalyticsEvent.event_type.in_(["rag_query", "knowledge_upload"]))
            .group_by(AnalyticsEvent.event_type)
            .all()
        )
        result["knowledge"] = {r.event_type: r.c for r in kb}

        # 工具统计
        tools = (
            db.query(AnalyticsEvent.event_type, func.count().label("c"))
            .filter(AnalyticsEvent.event_type == "tool_call")
            .all()
        )
        result["tools"] = {"total_calls": sum(r.c for r in tools)}

        # 最近评测
        latest_eval = (
            db.query(EvalRecord)
            .order_by(EvalRecord.created_at.desc())
            .first()
        )
        result["performance"] = {
            "latest_eval_accuracy": latest_eval.accuracy if latest_eval else None,
            "latest_eval_at": latest_eval.created_at.isoformat() if latest_eval and latest_eval.created_at else None,
        }

        db.close()
        return result
    except Exception:
        return {}


async def _get_cache_stats() -> float:
    """获取 RAG 缓存命中率"""
    try:
        from app.rag.cache import _cache
        return _cache.get_hit_rate() if hasattr(_cache, "get_hit_rate") else 0.0
    except Exception:
        return 0.0
