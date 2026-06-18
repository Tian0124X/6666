"""会话管理 — 多用户多会话隔离

存储策略:
- 主存储: Redis HSET  sessions:{user_id}  → {session_id -> JSON}
- 持久化: MySQL sessions 表
- 消息计数: 来自 Redis LLEN chat:{user_id}:{session_id} 或 MySQL COUNT
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import text as sa_text

from app.config import settings

logger = logging.getLogger(__name__)


def _redis_client():
    """获取 Redis 客户端（懒加载）"""
    try:
        from app.memory.store import _get_redis
        return _get_redis()
    except Exception:
        return None


def _mysql_session():
    """获取 MySQL 会话"""
    try:
        from app.models.database import get_session
        return get_session()
    except Exception:
        return None


def _get_preview(user_id: str, session_id: str) -> str:
    """获取会话首条消息的前 50 字作为预览"""
    redis = _redis_client()
    if redis:
        try:
            raw = redis.lindex(f"chat:{user_id}:{session_id}", 0)
            if raw:
                msg = json.loads(raw)
                content = msg.get("content", "")
                return content[:50] + ("…" if len(content) > 50 else "")
        except Exception:
            pass

    sess = _mysql_session()
    if sess:
        try:
            row = sess.execute(
                sa_text(
                    "SELECT content FROM conversations WHERE session_id = :sid AND user_id = :uid "
                    "ORDER BY created_at ASC LIMIT 1"
                ),
                {"sid": session_id, "uid": user_id},
            ).fetchone()
            if row:
                content = row[0] or ""
                return content[:50] + ("…" if len(content) > 50 else "")
        except Exception:
            pass
        finally:
            sess.close()

    return ""


def _get_message_count(user_id: str, session_id: str) -> int:
    """获取会话的消息数"""
    # Redis 优先
    redis = _redis_client()
    if redis:
        try:
            count = redis.llen(f"chat:{user_id}:{session_id}")
            if count:
                return count
        except Exception:
            pass

    # MySQL 兜底
    sess = _mysql_session()
    if sess:
        try:
            row = sess.execute(
                sa_text("SELECT COUNT(*) FROM conversations WHERE session_id = :sid AND user_id = :uid"),
                {"sid": session_id, "uid": user_id},
            ).fetchone()
            if row:
                return row[0]
        except Exception:
            pass
        finally:
            sess.close()

    return 0


def create_session(user_id: str, name: str = "新对话") -> dict:
    """创建新会话。返回 {session_id, name, user_id, created_at, message_count, preview}"""
    session_id = uuid.uuid4().hex[:16]  # 32 字符 → 16 字符够用
    now = datetime.now()

    session_data = {
        "session_id": session_id,
        "user_id": user_id,
        "name": name or "新对话",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "message_count": 0,
        "preview": "",
        "is_archived": 0,
    }

    # Redis
    redis = _redis_client()
    if redis:
        try:
            redis.hset(
                f"sessions:{user_id}",
                session_id,
                json.dumps(session_data, ensure_ascii=False),
            )
        except Exception as e:
            logger.warning(f"Redis 写 session 失败: {e}")

    # MySQL 持久化
    sess = _mysql_session()
    if sess:
        try:
            sess.execute(
                sa_text(
                    """INSERT INTO sessions (session_id, user_id, name, created_at, updated_at)
                       VALUES (:sid, :uid, :name, :ca, :ua)
                       ON DUPLICATE KEY UPDATE name = VALUES(name), updated_at = VALUES(updated_at)"""
                ),
                {"sid": session_id, "uid": user_id, "name": name or "新对话",
                 "ca": now, "ua": now},
            )
            sess.commit()
        except Exception as e:
            logger.warning(f"MySQL 写 session 失败: {e}")
        finally:
            sess.close()

    return session_data


def list_sessions(user_id: str) -> list[dict]:
    """列出用户的所有会话（按更新时间倒序）"""
    sessions = {}

    # Redis 优先
    redis = _redis_client()
    if redis:
        try:
            raw = redis.hgetall(f"sessions:{user_id}")
            for sid, data in raw.items():
                try:
                    sessions[sid] = json.loads(data)
                except json.JSONDecodeError:
                    sessions[sid] = {"session_id": sid, "name": "未知会话"}
        except Exception as e:
            logger.warning(f"Redis 读 session 列表失败: {e}")

    # MySQL 兜底 (补充 Redis 中没有的)
    if not sessions:
        sess = _mysql_session()
        if sess:
            try:
                rows = sess.execute(
                    sa_text(
                        """SELECT session_id, user_id, name, created_at, updated_at, is_archived
                           FROM sessions WHERE user_id = :uid
                           ORDER BY updated_at DESC LIMIT 100"""
                    ),
                    {"uid": user_id},
                ).fetchall()
                for row in rows:
                    sid = row[0]
                    if sid not in sessions:
                        sessions[sid] = {
                            "session_id": sid,
                            "user_id": row[1],
                            "name": row[2],
                            "created_at": row[3].isoformat() if row[3] else "",
                            "updated_at": row[4].isoformat() if row[4] else "",
                            "message_count": 0,
                            "preview": "",
                            "is_archived": row[5] if len(row) > 5 else 0,
                        }
            except Exception as e:
                logger.warning(f"MySQL 读 session 列表失败: {e}")
            finally:
                sess.close()

    # 补消息数 + preview + 排序
    result = []
    for sid, s in sessions.items():
        s["message_count"] = _get_message_count(user_id, sid)
        if not s.get("preview"):
            s["preview"] = _get_preview(user_id, sid)
        result.append(s)

    result.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return result


def delete_session(session_id: str, user_id: str) -> bool:
    """删除会话 + 其所有消息。需校验所有权。"""
    redis = _redis_client()
    owned = False

    if redis:
        try:
            data = redis.hget(f"sessions:{user_id}", session_id)
            if data:
                owned = True
                redis.hdel(f"sessions:{user_id}", session_id)
                redis.delete(f"chat:{user_id}:{session_id}")
        except Exception:
            pass

    # MySQL
    sess = _mysql_session()
    if sess:
        try:
            row = sess.execute(
                sa_text("SELECT session_id FROM sessions WHERE session_id = :sid AND user_id = :uid"),
                {"sid": session_id, "uid": user_id},
            ).fetchone()
            if row:
                owned = True
                sess.execute(
                    sa_text("DELETE FROM sessions WHERE session_id = :sid AND user_id = :uid"),
                    {"sid": session_id, "uid": user_id},
                )
                sess.execute(
                    sa_text("DELETE FROM conversations WHERE session_id = :sid AND user_id = :uid"),
                    {"sid": session_id, "uid": user_id},
                )
                sess.commit()
        except Exception as e:
            logger.warning(f"MySQL 删 session 失败: {e}")
        finally:
            sess.close()

    if not owned:
        return False

    # 清理内存
    try:
        from app.memory.store import get_memory_store
        import asyncio
        async def _clear():
            store = await get_memory_store()
            await store.clear(session_id, user_id)
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(_clear())
        except RuntimeError:
            # 没有运行中的 event loop，直接同步清理内存 dict
            try:
                from app.memory.store import _memory_store_instance
                if _memory_store_instance:
                    _memory_store_instance._store.pop(f"chat:{user_id}:{session_id}", None)
            except Exception:
                pass
    except Exception:
        pass

    return True


def rename_session(session_id: str, user_id: str, new_name: str) -> bool:
    """重命名会话。需校验所有权。"""
    if not new_name or not new_name.strip():
        return False
    new_name = new_name.strip()[:128]

    redis = _redis_client()
    owned = False

    if redis:
        try:
            raw = redis.hget(f"sessions:{user_id}", session_id)
            if raw:
                owned = True
                data = json.loads(raw)
                data["name"] = new_name
                data["updated_at"] = datetime.now().isoformat()
                redis.hset(f"sessions:{user_id}", session_id, json.dumps(data, ensure_ascii=False))
        except Exception:
            pass

    sess = _mysql_session()
    if sess:
        try:
            row = sess.execute(
                sa_text("SELECT session_id FROM sessions WHERE session_id = :sid AND user_id = :uid"),
                {"sid": session_id, "uid": user_id},
            ).fetchone()
            if row:
                owned = True
                sess.execute(
                    sa_text("UPDATE sessions SET name = :name, updated_at = NOW() WHERE session_id = :sid AND user_id = :uid"),
                    {"name": new_name, "sid": session_id, "uid": user_id},
                )
                sess.commit()
        except Exception as e:
            logger.warning(f"MySQL 改 session 名失败: {e}")
        finally:
            sess.close()

    return owned


def archive_session(session_id: str, user_id: str, archived: bool = True) -> bool:
    """归档/取消归档会话"""
    redis = _redis_client()
    owned = False

    if redis:
        try:
            raw = redis.hget(f"sessions:{user_id}", session_id)
            if raw:
                owned = True
                data = json.loads(raw)
                data["is_archived"] = 1 if archived else 0
                data["updated_at"] = datetime.now().isoformat()
                redis.hset(f"sessions:{user_id}", session_id, json.dumps(data, ensure_ascii=False))
        except Exception:
            pass

    sess = _mysql_session()
    if sess:
        try:
            row = sess.execute(
                sa_text("SELECT session_id FROM sessions WHERE session_id = :sid AND user_id = :uid"),
                {"sid": session_id, "uid": user_id},
            ).fetchone()
            if row:
                owned = True
                sess.execute(
                    sa_text("UPDATE sessions SET is_archived = :a, updated_at = NOW() WHERE session_id = :sid AND user_id = :uid"),
                    {"a": 1 if archived else 0, "sid": session_id, "uid": user_id},
                )
                sess.commit()
        except Exception as e:
            logger.warning(f"MySQL 归档 session 失败: {e}")
        finally:
            sess.close()

    return owned


def get_session_owner(session_id: str) -> Optional[str]:
    """查询 session 归属用户（用于权限校验）"""
    redis = _redis_client()
    if redis:
        try:
            # 扫描所有 user 的 sessions hash
            for key in redis.scan_iter("sessions:*"):
                if redis.hexists(key, session_id):
                    return key.split(":", 1)[1]  # sessions:{user_id}
        except Exception:
            pass

    sess = _mysql_session()
    if sess:
        try:
            row = sess.execute(
                sa_text("SELECT user_id FROM sessions WHERE session_id = :sid"),
                {"sid": session_id},
            ).fetchone()
            if row:
                return row[0]
        except Exception:
            pass
        finally:
            sess.close()

    return None
