"""
三级记忆存储 — Redis(L1) → 内存(L2) → MySQL(L3)

读取路径: Redis → 内存 → MySQL (级联回填)
写入路径: 内存 + Redis (同步) → MySQL (异步)
"""

import asyncio
import json
import logging
from typing import List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from sqlalchemy import text as sa_text

from app.config import settings

logger = logging.getLogger(__name__)

# ====== 数据模型 ======


@dataclass
class ConversationMessage:
    role: str  # user | assistant | system
    content: str
    metadata: Optional[dict] = None  # 图表/表格/洞察等富数据
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        d: dict = {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
        }
        if self.metadata:
            d["metadata"] = self.metadata
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationMessage":
        msg = cls(
            data.get("role", "unknown"),
            data.get("content", ""),
            metadata=data.get("metadata"),
        )
        ts = data.get("timestamp")
        if ts:
            msg.timestamp = datetime.fromisoformat(ts)
        return msg

    @classmethod
    def from_json(cls, s: str) -> "ConversationMessage":
        return cls.from_dict(json.loads(s))


# ====== Redis 客户端 (懒加载) ======

_redis_client: Optional[object] = None
_redis_available: bool = False


def _get_redis():
    """获取 Redis 连接（带降级标志）"""
    global _redis_client, _redis_available
    if _redis_client is not None:
        return _redis_client if _redis_available else None

    try:
        import redis
        _redis_client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, decode_responses=True)
        _redis_client.ping()
        _redis_available = True
        logger.info("✅ Redis L1 缓存就绪")
    except Exception as e:
        _redis_client = False  # type: ignore
        _redis_available = False
        logger.warning(f"Redis 不可用，降级到内存: {e}")
    return _redis_client if _redis_available else None


# ====== MySQL 持久化 ======

def _mysql_save(session_id: str, user_id: str, role: str, content: str, metadata: Optional[dict] = None):
    """同步保存到 MySQL（在后台线程执行）"""
    from app.models.database import get_session, ConversationRecord
    sess = get_session()
    if sess is None:
        return
    try:
        record = ConversationRecord(
            session_id=session_id, user_id=user_id,
            role=role, content=content,
            metadata_json=metadata,
        )
        sess.add(record)
        sess.commit()
    except Exception as e:
        logger.warning(f"MySQL 写入失败: {e}")
    finally:
        sess.close()


def _mysql_load(session_id: str, user_id: str, limit: int = 20) -> List[ConversationMessage]:
    """从 MySQL 加载历史消息"""
    from app.models.database import get_session, ConversationRecord
    sess = get_session()
    if sess is None:
        return []
    try:
        from sqlalchemy import desc
        records = (
            sess.query(ConversationRecord)
            .filter(
                ConversationRecord.session_id == session_id,
                ConversationRecord.user_id == user_id,
            )
            .order_by(desc(ConversationRecord.created_at))
            .limit(limit)
            .all()
        )
        # 按时间正序返回
        records = list(reversed(records))
        return [
            ConversationMessage(
                role=r.role, content=r.content,
                metadata=r.metadata_json if hasattr(r, 'metadata_json') else None,
                timestamp=r.created_at,
            )
            for r in records
        ]
    except Exception as e:
        logger.warning(f"MySQL 读取失败: {e}")
        return []
    finally:
        sess.close()


def _mysql_clear(session_id: str, user_id: str):
    """清空 MySQL 中的会话记录"""
    from app.models.database import get_session, ConversationRecord
    sess = get_session()
    if sess is None:
        return
    try:
        sess.query(ConversationRecord).filter(
            ConversationRecord.session_id == session_id,
            ConversationRecord.user_id == user_id,
        ).delete()
        sess.commit()
    except Exception as e:
        logger.warning(f"MySQL 清空失败: {e}")
    finally:
        sess.close()


# ====== 三级 MemoryStore ======


class MemoryStore:
    """
    三级记忆存储: Redis(L1) → 内存(L2) → MySQL(L3)

    读: Redis → 内存 → MySQL (级联回填)
    写: 内存(同步) + Redis(同步) + MySQL(异步)
    """

    REDIS_TTL = 3600  # Redis key 过期时间 (秒)
    WINDOW_SIZE = 20  # 上下文窗口大小

    def __init__(self, window_size: int = 20):
        self.window_size = window_size
        self._store: dict[str, List[ConversationMessage]] = {}
        self._lock = asyncio.Lock()

    def _make_key(self, session_id: str, user_id: str) -> str:
        return f"chat:{user_id}:{session_id}"

    # ---- 读路径: Redis → 内存 → MySQL ----

    def get_history(self, session_id: str, user_id: str) -> List[ConversationMessage]:
        """获取对话历史（三级级联读取）"""
        key = self._make_key(session_id, user_id)

        # L1: 内存 (最快)
        if key in self._store:
            return self._store[key][-(self.window_size * 2):]

        # L2: Redis
        redis = _get_redis()
        if redis:
            try:
                raw = redis.lrange(key, -40, -1)
                if raw:
                    messages = [ConversationMessage.from_json(m) for m in raw]
                    self._store[key] = messages  # 回填内存
                    return messages
            except Exception as e:
                logger.warning(f"Redis 读取失败: {e}")

        # L3: MySQL
        messages = _mysql_load(session_id, user_id, self.window_size * 2)
        if messages:
            self._store[key] = messages  # 回填内存
            # 回填 Redis
            if redis:
                try:
                    pipe = redis.pipeline()
                    for m in messages:
                        pipe.rpush(key, m.to_json())
                    pipe.expire(key, self.REDIS_TTL)
                    pipe.execute()
                except Exception:
                    pass
        return messages

    # ---- 写路径: 内存 + Redis (同步) → MySQL (异步) ----

    async def add_message(self, session_id: str, user_id: str, role: str, content: str, metadata: Optional[dict] = None):
        """添加消息到所有存储层"""
        msg = ConversationMessage(role, content, metadata=metadata)
        key = self._make_key(session_id, user_id)

        # L1: 内存 (同步 + 锁保护)
        async with self._lock:
            if key not in self._store:
                self._store[key] = []
            self._store[key].append(msg)
            if len(self._store[key]) > self.window_size * 4:
                self._store[key] = self._store[key][-(self.window_size * 2):]

        # L2: Redis (同步)
        redis = _get_redis()
        if redis:
            try:
                pipe = redis.pipeline()
                pipe.rpush(key, msg.to_json())
                pipe.expire(key, self.REDIS_TTL)
                pipe.execute()
            except Exception as e:
                logger.warning(f"Redis 写入失败: {e}")

        # L3: MySQL (异步后台写入)
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, _mysql_save, session_id, user_id, role, content, metadata)
        except RuntimeError:
            _mysql_save(session_id, user_id, role, content, metadata)

    # ---- 会话枚举 ----

    async def list_user_session_ids(self, user_id: str) -> list[str]:
        """列出某用户在 Redis 中的所有 session_id"""
        ids = set()
        redis = _get_redis()
        if redis:
            try:
                for key in redis.scan_iter(f"chat:{user_id}:*"):
                    sid = key.split(":", 2)[-1]
                    if sid:
                        ids.add(sid)
            except Exception:
                pass

        # 也查 MySQL
        from app.models.database import get_session, ConversationRecord
        sess = get_session()
        if sess:
            try:
                rows = sess.execute(
                    sa_text("SELECT DISTINCT session_id FROM conversations WHERE user_id = :uid"),
                    {"uid": user_id},
                ).fetchall()
                for row in rows:
                    ids.add(row[0])
            except Exception:
                pass
            finally:
                sess.close()

        return sorted(ids, reverse=True)

    # ---- 清空 ----

    async def clear(self, session_id: str, user_id: str):
        """清空所有层的会话数据"""
        key = self._make_key(session_id, user_id)

        async with self._lock:
            self._store.pop(key, None)

        redis = _get_redis()
        if redis:
            try:
                redis.delete(key)
            except Exception:
                pass

        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, _mysql_clear, session_id, user_id)
        except RuntimeError:
            _mysql_clear(session_id, user_id)


# ====== 全局单例 ======

_memory_store_instance: Optional[MemoryStore] = None
_store_lock = asyncio.Lock()


async def get_memory_store() -> MemoryStore:
    """异步获取 MemoryStore 单例（线程安全）"""
    global _memory_store_instance
    if _memory_store_instance is None:
        async with _store_lock:
            if _memory_store_instance is None:
                _memory_store_instance = MemoryStore()
    return _memory_store_instance
