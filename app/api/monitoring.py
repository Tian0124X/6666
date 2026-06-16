"""
LLMOps 监控 API — 借鉴 Dify LLMOps 设计

提供: API 调用统计 / 延迟追踪 / Token 估算 / 工具调用计数
2026 修复: Redis 持久化 + 中间件注册 + 工具/Token追踪集成
"""

import time
import json
import logging
import asyncio
from collections import defaultdict
from datetime import datetime
from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# ====== Redis 持久化存储 ======

class MonitoringStore:
    """
    内存 + Redis 双层存储。
    - 内存缓存: 快速读取，服务于 /api/stats 等高频访问
    - Redis 持久化: 服务重启不丢数据
    - Redis 不可用时自动降级为纯内存
    """

    def __init__(self):
        self._redis = None
        self._redis_available = False
        self._redis_checked = False

        # 内存统计 (始终有效)
        self.total_requests = 0
        self.total_success = 0
        self.total_errors = 0
        self.total_latency_ms = 0.0
        self.total_tokens = 0
        self.by_endpoint: dict = defaultdict(lambda: {"count": 0, "total_ms": 0.0, "errors": 0})
        self.by_hour: dict = defaultdict(int)
        self.tool_calls: dict = defaultdict(int)
        self.ratings: list = []  # [(score, comment), ...]
        self.recent_requests: list = []  # 最近 50 条
        self.start_time = datetime.now().isoformat()

    async def _init_redis(self):
        """懒加载 Redis 连接"""
        if self._redis_checked:
            return
        self._redis_checked = True
        try:
            import redis.asyncio as redis
            from app.config import settings
            self._redis = redis.from_url(
                settings.REDIS_URL,
                socket_connect_timeout=2,
                decode_responses=True,
            )
            await self._redis.ping()
            self._redis_available = True
            logger.info("监控 Redis 持久化就绪")
            # 从 Redis 加载历史数据
            await self._load_from_redis()
        except Exception as e:
            logger.warning(f"监控 Redis 不可用 ({e})，降级为纯内存模式")

    async def _load_from_redis(self):
        """从 Redis 恢复历史数据 (仅在 Redis 有数据时覆盖内存值)"""
        try:
            r = self._redis

            # 只在内存值为0时从Redis恢复 (Redis无数据时不覆盖)
            v = await r.get("mon:total_requests")
            if v is not None and self.total_requests == 0:
                self.total_requests = int(v)
            v = await r.get("mon:total_success")
            if v is not None and self.total_success == 0:
                self.total_success = int(v)
            v = await r.get("mon:total_errors")
            if v is not None and self.total_errors == 0:
                self.total_errors = int(v)
            v = await r.get("mon:total_latency_ms")
            if v is not None and self.total_latency_ms == 0:
                self.total_latency_ms = float(v)
            v = await r.get("mon:total_tokens")
            if v is not None and self.total_tokens == 0:
                self.total_tokens = int(v)

            # by_endpoint (hash → dict, 合并而非覆盖)
            ep_data = await r.hgetall("mon:by_endpoint")
            for k, v in ep_data.items():
                if k not in self.by_endpoint or self.by_endpoint[k]["count"] == 0:
                    self.by_endpoint[k] = json.loads(v)

            # by_hour (合并)
            hour_data = await r.hgetall("mon:by_hour")
            for k, v in hour_data.items():
                if k not in self.by_hour:
                    self.by_hour[k] = int(v)

            # tool_calls (合并)
            tool_data = await r.hgetall("mon:tool_calls")
            for k, v in tool_data.items():
                if k not in self.tool_calls:
                    self.tool_calls[k] = int(v)

            # ratings (仅追加)
            rating_data = await r.lrange("mon:ratings", 0, -1)
            if rating_data and not self.ratings:
                for item in rating_data:
                    try:
                        self.ratings.append(json.loads(item))
                    except Exception:
                        pass

            # recent_requests (仅追加)
            req_data = await r.lrange("mon:recent_requests", 0, -1)
            if req_data and not self.recent_requests:
                for item in req_data:
                try:
                    self.recent_requests.append(json.loads(item))
                except Exception:
                    pass

            # start_time
            saved_start = await r.get("mon:start_time")
            if saved_start:
                self.start_time = saved_start

            logger.info(
                f"监控数据已从 Redis 恢复: {self.total_requests} 请求, "
                f"{len(self.by_endpoint)} 端点, {len(self.tool_calls)} 工具"
            )
        except Exception as e:
            logger.warning(f"Redis 数据加载失败: {e}")

    async def _sync_counter(self, key: str, value):
        """同步计数器到 Redis"""
        if not self._redis_available:
            return
        try:
            await self._redis.set(f"mon:{key}", value)
        except Exception:
            pass

    async def _sync_hash(self, key: str, field: str, value):
        """同步 hash 字段到 Redis"""
        if not self._redis_available:
            return
        try:
            await self._redis.hset(f"mon:{key}", field, value)
        except Exception:
            pass

    async def _sync_list_push(self, key: str, value: str, maxlen: int = 100):
        """追加到 Redis list 并修剪"""
        if not self._redis_available:
            return
        try:
            pipe = self._redis.pipeline()
            pipe.lpush(f"mon:{key}", value)
            pipe.ltrim(f"mon:{key}", 0, maxlen - 1)
            await pipe.execute()
        except Exception:
            pass

    # ====== 公开追踪方法 ======

    async def track_request(self, method: str, path: str, status: int, elapsed_ms: float, error: bool = False):
        """记录一次 API 请求"""
        await self._init_redis()

        self.total_requests += 1
        self.total_latency_ms += elapsed_ms

        endpoint_key = f"{method} {path}"
        ep = self.by_endpoint[endpoint_key]
        ep["count"] += 1
        ep["total_ms"] += elapsed_ms
        if error or status >= 400:
            self.total_errors += 1
            ep["errors"] += 1
        else:
            self.total_success += 1

        # 按小时
        hour_key = datetime.now().strftime("%H:00")
        self.by_hour[hour_key] += 1

        # 最近请求
        req_entry = {
            "time": datetime.now().isoformat(),
            "method": method,
            "path": path,
            "status": status,
            "latency_ms": round(elapsed_ms, 1),
        }
        self.recent_requests.append(req_entry)
        if len(self.recent_requests) > 50:
            self.recent_requests = self.recent_requests[-50:]

        # 异步同步到 Redis (fire-and-forget)
        asyncio.create_task(self._persist_request(method, path, status, elapsed_ms, error, hour_key, req_entry))

    async def _persist_request(self, method, path, status, elapsed_ms, error, hour_key, req_entry):
        """后台异步写入 Redis"""
        await self._sync_counter("total_requests", self.total_requests)
        await self._sync_counter("total_success", self.total_success)
        await self._sync_counter("total_errors", self.total_errors)
        await self._sync_counter("total_latency_ms", self.total_latency_ms)
        endpoint_key = f"{method} {path}"
        await self._sync_hash("by_endpoint", endpoint_key, json.dumps(self.by_endpoint[endpoint_key]))
        await self._sync_hash("by_hour", hour_key, self.by_hour[hour_key])
        await self._sync_list_push("recent_requests", json.dumps(req_entry), maxlen=50)

    def track_tool_call(self, tool_name: str):
        """记录一次工具调用 (同步, 异步写 Redis)"""
        self.tool_calls[tool_name] += 1
        asyncio.create_task(self._persist_tool_call(tool_name))

    async def _persist_tool_call(self, tool_name: str):
        await self._init_redis()
        await self._sync_hash("tool_calls", tool_name, self.tool_calls[tool_name])

    def track_token_usage(self, count: int):
        """记录 token 消耗 (同步, 异步写 Redis)"""
        self.total_tokens += count
        asyncio.create_task(self._persist_token())

    async def _persist_token(self):
        await self._init_redis()
        await self._sync_counter("total_tokens", self.total_tokens)

    def add_rating(self, score: int, comment: str = ""):
        """记录对话评分"""
        entry = (score, comment)
        self.ratings.append(entry)
        asyncio.create_task(self._persist_rating(score, comment))

    async def _persist_rating(self, score: int, comment: str):
        await self._init_redis()
        await self._sync_list_push("ratings", json.dumps([score, comment]), maxlen=100)

    # ====== 查询方法 ======

    def get_stats(self) -> dict:
        """获取完整统计"""
        total = max(self.total_requests, 1)
        avg_latency = round(self.total_latency_ms / total, 1)
        error_rate = round(self.total_errors / total * 100, 1)

        top_endpoints = sorted(
            [{"endpoint": k, **v, "avg_ms": round(v["total_ms"] / max(v["count"], 1), 1)}
             for k, v in self.by_endpoint.items()],
            key=lambda x: x["count"], reverse=True,
        )[:10]

        top_tools = sorted(
            [{"tool": k, "calls": v} for k, v in self.tool_calls.items()],
            key=lambda x: x["calls"], reverse=True,
        )

        hourly = [{"hour": k, "count": v} for k, v in sorted(self.by_hour.items())]

        avg_rating = round(sum(r[0] for r in self.ratings) / max(len(self.ratings), 1), 1) if self.ratings else None

        return {
            "overview": {
                "total_requests": self.total_requests,
                "success": self.total_success,
                "errors": self.total_errors,
                "error_rate_pct": error_rate,
                "avg_latency_ms": avg_latency,
                "total_tokens": self.total_tokens,
            },
            "avg_rating": avg_rating,
            "rating_count": len(self.ratings),
            "top_endpoints": top_endpoints,
            "top_tools": top_tools,
            "hourly_requests": hourly[-24:],
            "recent_requests": self.recent_requests[-20:],
            "uptime_since": self.start_time,
        }

    def get_dashboard(self) -> dict:
        """监控面板简化摘要"""
        total = max(self.total_requests, 1)
        avg_rating = round(sum(r[0] for r in self.ratings) / max(len(self.ratings), 1), 1) if self.ratings else None
        return {
            "requests_total": self.total_requests,
            "success_rate": round(self.total_success / total * 100, 1),
            "avg_latency_ms": round(self.total_latency_ms / total, 1),
            "errors_today": self.total_errors,
            "avg_rating": avg_rating,
            "tools_used": len(self.tool_calls),
        }


# 全局单例
_store = MonitoringStore()


# ====== FastAPI 中间件 ======

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
        status = response.status_code if response else 500
        await _store.track_request(
            method=request.method,
            path=request.url.path,
            status=status,
            elapsed_ms=elapsed_ms,
            error=error,
        )


# ====== 内部追踪函数 (供其他模块调用) ======

def track_tool_call(tool_name: str):
    """内部函数: 记录一次工具调用"""
    _store.track_tool_call(tool_name)


def track_token_usage(count: int):
    """内部函数: 记录 token 消耗"""
    _store.track_token_usage(count)


# ====== 公开统计 API ======


@router.get("/stats", tags=["监控"])
async def get_stats():
    """LLMOps 总览统计"""
    return _store.get_stats()


@router.get("/stats/dashboard", tags=["监控"])
async def dashboard_summary():
    """监控面板 — 简化摘要"""
    return _store.get_dashboard()


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

    _store.add_rating(req.score, req.comment)
    logger.info(f"对话评分: {req.score}⭐ | {req.comment[:50] if req.comment else ''}")
    return {"status": "ok", "message": "感谢您的反馈!"}
