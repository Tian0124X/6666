"""可选 Redis JSON 缓存：只加速读取，不承担记忆持久化责任。"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class OptionalRedisJsonCache:
    """Redis 不可用时自动退化为空缓存，避免影响 RAG 主链路。"""

    def __init__(self) -> None:
        self._client: Any | None = None
        self._unavailable = False

    def _get_client(self) -> Any | None:
        if self._unavailable:
            return None
        if self._client is not None:
            return self._client
        try:
            import redis

            client = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
            )
            client.ping()
            self._client = client
            return client
        except Exception as exc:
            self._unavailable = True
            logger.info("Redis 记忆缓存不可用，继续使用 MySQL/进程内缓存: %s", exc)
            return None

    def get_json(self, key: str) -> Any | None:
        """读取 JSON；缓存损坏时按未命中处理。"""
        client = self._get_client()
        if client is None:
            return None
        try:
            raw = client.get(key)
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.warning("读取 Redis 记忆缓存失败: %s", exc)
            return None

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        """写入带过期时间的 JSON 缓存。"""
        client = self._get_client()
        if client is None:
            return
        try:
            client.setex(key, ttl_seconds, json.dumps(value, ensure_ascii=False))
        except Exception as exc:
            logger.warning("写入 Redis 记忆缓存失败: %s", exc)

    def delete(self, key: str) -> None:
        """删除可能过期的缓存副本。"""
        client = self._get_client()
        if client is None:
            return
        try:
            client.delete(key)
        except Exception as exc:
            logger.warning("删除 Redis 记忆缓存失败: %s", exc)


memory_cache = OptionalRedisJsonCache()
