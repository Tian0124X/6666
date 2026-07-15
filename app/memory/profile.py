"""用户显式偏好记忆：可查看、可删除，绝不自动猜测和写入。"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

from app.models.database import UserFact, get_session
from app.memory.cache import memory_cache

logger = logging.getLogger(__name__)


class UserPreferenceStore:
    """保存只影响回答表达方式的用户偏好，不存知识事实。"""

    def __init__(self) -> None:
        self._fallback: dict[str, list[dict[str, str]]] = defaultdict(list)
        self._fallback_id = 0

    def list_preferences(self, user_id: str, limit: int = 5) -> list[dict[str, str]]:
        """读取已确认偏好；匿名用户不读取用户记忆，避免多人共享。"""
        if user_id == "anonymous":
            return []
        cache_key = self._cache_key(user_id)
        cached = memory_cache.get_json(cache_key)
        if self._is_valid_preference_list(cached):
            return cached[:limit]
        db = get_session()
        if db is not None:
            try:
                records = (
                    db.query(UserFact)
                    .filter(UserFact.user_id == user_id, UserFact.category == "preference")
                    .order_by(UserFact.last_accessed_at.desc(), UserFact.id.desc())
                    .limit(limit)
                    .all()
                )
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                for record in records:
                    record.last_accessed_at = now
                    record.access_count = int(record.access_count or 0) + 1
                if records:
                    db.commit()
                preferences = [{"id": str(record.id), "fact_text": record.fact_text} for record in records]
                memory_cache.set_json(cache_key, preferences, ttl_seconds=3600)
                return preferences
            except Exception as exc:
                db.rollback()
                logger.warning("读取用户偏好失败，降级使用进程内缓存: %s", exc)
            finally:
                db.close()
        return self._fallback[user_id][-limit:]

    def save_preference(self, user_id: str, fact_text: str, session_id: str | None = None) -> dict[str, str]:
        """仅保存用户明确提交的偏好；相同偏好去重。"""
        text = fact_text.strip()
        if not text:
            raise ValueError("偏好不能为空")
        if user_id == "anonymous":
            raise ValueError("访客无法保存跨会话偏好，请先登录")

        db = get_session()
        if db is not None:
            try:
                record = (
                    db.query(UserFact)
                    .filter(
                        UserFact.user_id == user_id,
                        UserFact.category == "preference",
                        UserFact.fact_text == text,
                    )
                    .one_or_none()
                )
                if record is None:
                    record = UserFact(
                        user_id=user_id,
                        fact_text=text,
                        category="preference",
                        confidence="1.0",
                        source_session_id=session_id,
                    )
                    db.add(record)
                    db.flush()
                db.commit()
                memory_cache.delete(self._cache_key(user_id))
                return {"id": str(record.id), "fact_text": record.fact_text}
            except Exception as exc:
                db.rollback()
                logger.warning("写入用户偏好失败，降级使用进程内缓存: %s", exc)
            finally:
                db.close()

        existing = next((item for item in self._fallback[user_id] if item["fact_text"] == text), None)
        if existing is not None:
            return existing
        self._fallback_id += 1
        entry = {"id": f"local-{self._fallback_id}", "fact_text": text}
        self._fallback[user_id].append(entry)
        memory_cache.delete(self._cache_key(user_id))
        return entry

    def delete_preference(self, user_id: str, preference_id: str) -> bool:
        """删除用户主动选择遗忘的偏好。"""
        db = get_session()
        if db is not None:
            try:
                record = (
                    db.query(UserFact)
                    .filter(
                        UserFact.id == preference_id,
                        UserFact.user_id == user_id,
                        UserFact.category == "preference",
                    )
                    .one_or_none()
                )
                if record is None:
                    return False
                db.delete(record)
                db.commit()
                memory_cache.delete(self._cache_key(user_id))
                return True
            except Exception as exc:
                db.rollback()
                logger.warning("删除用户偏好失败: %s", exc)
                return False
            finally:
                db.close()

        entries = self._fallback[user_id]
        remaining = [item for item in entries if item["id"] != preference_id]
        if len(remaining) == len(entries):
            return False
        self._fallback[user_id] = remaining
        memory_cache.delete(self._cache_key(user_id))
        return True

    @staticmethod
    def _cache_key(user_id: str) -> str:
        return f"rag:memory:user:{user_id}:preferences"

    @staticmethod
    def _is_valid_preference_list(value: object) -> bool:
        return isinstance(value, list) and all(
            isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and isinstance(item.get("fact_text"), str)
            for item in value
        )


user_preference_memory = UserPreferenceStore()
