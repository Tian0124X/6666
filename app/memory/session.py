"""RAG 会话记忆：优先持久化到 MySQL，不可用时降级为进程内缓存。"""

from __future__ import annotations

import logging
import json
from collections import defaultdict
from typing import Literal

from app.models.database import ConversationRecord, ConversationSummary, get_session
from app.memory.cache import memory_cache

logger = logging.getLogger(__name__)

MemoryRole = Literal["user", "assistant"]


class SessionMemoryStore:
    """只保存已完成的问答，向 RAG 提供有限且有边界的近期上下文。"""

    def __init__(self, fallback_turn_limit: int = 24) -> None:
        self._fallback_turn_limit = fallback_turn_limit
        self._fallback: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        self._fallback_summaries: dict[tuple[str, str], str] = {}

    def get_recent_turns(self, user_id: str, session_id: str, limit: int = 6) -> list[dict[str, str]]:
        """读取当前用户、当前会话的最近消息，避免跨用户和跨会话串记忆。"""
        cache_key = self._turns_cache_key(user_id, session_id)
        cached = memory_cache.get_json(cache_key)
        if self._is_valid_turn_list(cached):
            self._fallback[(user_id, session_id)] = cached[-self._fallback_turn_limit:]
            return cached[-limit:]
        db = get_session()
        if db is not None:
            try:
                records = (
                    db.query(ConversationRecord)
                    .filter(
                        ConversationRecord.user_id == user_id,
                        ConversationRecord.session_id == session_id,
                        ConversationRecord.role.in_(("user", "assistant")),
                    )
                    .order_by(ConversationRecord.id.desc())
                    .limit(limit)
                    .all()
                )
                turns = [
                    {"role": record.role, "content": record.content}
                    for record in reversed(records)
                ]
                self._fallback[(user_id, session_id)] = turns[-self._fallback_turn_limit:]
                memory_cache.set_json(cache_key, turns, ttl_seconds=3600)
                return turns
            except Exception as exc:
                logger.warning("读取会话记忆失败，降级使用进程内缓存: %s", exc)
            finally:
                db.close()
        return self._fallback[(user_id, session_id)][-limit:]

    def append_turn(self, user_id: str, session_id: str, role: MemoryRole, content: str) -> None:
        """保存一条完成的用户或助手消息；失败不会影响 RAG 主回答链路。"""
        text = content.strip()
        if not text:
            return

        entry = {"role": role, "content": text}
        bucket = self._fallback[(user_id, session_id)]
        bucket.append(entry)
        del bucket[:-self._fallback_turn_limit]
        memory_cache.set_json(self._turns_cache_key(user_id, session_id), bucket, ttl_seconds=3600)

        db = get_session()
        if db is None:
            return
        try:
            db.add(ConversationRecord(
                user_id=user_id,
                session_id=session_id,
                role=role,
                content=text,
                metadata_json={"channel": "rag"},
            ))
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("写入会话记忆失败，已保留进程内副本: %s", exc)
        finally:
            db.close()

    def get_summary(self, user_id: str, session_id: str) -> str:
        """读取当前会话的滚动摘要，摘要不含任何知识库事实断言。"""
        cache_key = self._summary_cache_key(user_id, session_id)
        cached = memory_cache.get_json(cache_key)
        if isinstance(cached, str):
            self._fallback_summaries[(user_id, session_id)] = cached
            return cached
        db = get_session()
        if db is not None:
            try:
                record = (
                    db.query(ConversationSummary)
                    .filter(
                        ConversationSummary.user_id == user_id,
                        ConversationSummary.session_id == session_id,
                    )
                    .one_or_none()
                )
                if record is not None:
                    try:
                        payload = json.loads(record.summary_json)
                        summary = str(payload.get("summary", "")).strip()
                    except (TypeError, ValueError):
                        summary = record.summary_json.strip()
                    self._fallback_summaries[(user_id, session_id)] = summary
                    memory_cache.set_json(cache_key, summary, ttl_seconds=86400)
                    return summary
            except Exception as exc:
                logger.warning("读取会话摘要失败，降级使用进程内缓存: %s", exc)
            finally:
                db.close()
        return self._fallback_summaries.get((user_id, session_id), "")

    def refresh_summary(
        self,
        user_id: str,
        session_id: str,
        trigger_turns: int = 8,
        source_turns: int = 16,
    ) -> str:
        """以抽取式规则生成滚动摘要，避免为记忆额外调用模型并引入幻觉。"""
        turns = self.get_recent_turns(user_id, session_id, limit=source_turns)
        if len(turns) < trigger_turns:
            return self.get_summary(user_id, session_id)

        summary = self._build_extractive_summary(turns)
        self._fallback_summaries[(user_id, session_id)] = summary
        memory_cache.set_json(self._summary_cache_key(user_id, session_id), summary, ttl_seconds=86400)
        db = get_session()
        if db is None:
            return summary
        try:
            record = (
                db.query(ConversationSummary)
                .filter(
                    ConversationSummary.user_id == user_id,
                    ConversationSummary.session_id == session_id,
                )
                .one_or_none()
            )
            payload = json.dumps(
                {"summary": summary, "turn_count": len(turns), "strategy": "extractive_v1"},
                ensure_ascii=False,
            )
            if record is None:
                db.add(ConversationSummary(
                    user_id=user_id,
                    session_id=session_id,
                    summary_json=payload,
                    is_final=0,
                ))
            else:
                record.summary_json = payload
                record.is_final = 0
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("写入会话摘要失败，已保留进程内副本: %s", exc)
        finally:
            db.close()
        return summary

    @staticmethod
    def _build_extractive_summary(turns: list[dict[str, str]]) -> str:
        """只压缩用户目标和已给出的回复片段，不创造新结论。"""
        user_messages = [turn["content"].strip()[:180] for turn in turns if turn["role"] == "user"]
        assistant_messages = [turn["content"].strip()[:220] for turn in turns if turn["role"] == "assistant"]
        sections: list[str] = []
        if user_messages:
            sections.append("用户近期关注：" + "；".join(user_messages[-4:]))
        if assistant_messages:
            sections.append("已给出回复：" + "；".join(assistant_messages[-3:]))
        return "\n".join(sections)[:1600]

    @staticmethod
    def _turns_cache_key(user_id: str, session_id: str) -> str:
        return f"rag:memory:session:{user_id}:{session_id}:turns"

    @staticmethod
    def _summary_cache_key(user_id: str, session_id: str) -> str:
        return f"rag:memory:session:{user_id}:{session_id}:summary"

    @staticmethod
    def _is_valid_turn_list(value: object) -> bool:
        return isinstance(value, list) and all(
            isinstance(item, dict)
            and item.get("role") in {"user", "assistant"}
            and isinstance(item.get("content"), str)
            for item in value
        )


session_memory = SessionMemoryStore()
