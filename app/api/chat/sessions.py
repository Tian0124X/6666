"""会话管理 + 对话历史端点"""

import json
import logging

from fastapi import APIRouter, HTTPException, Query, Depends

from app.config import settings
from app.memory.store import get_memory_store
from app.models.user import UserInfo
from app.api.auth import require_user

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# 会话 CRUD
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/sessions", tags=["会话"])
async def create_session(
    user: UserInfo = Depends(require_user),
    name: str = Query(default="新对话", description="会话名称"),
):
    """创建新会话。返回 session_id。"""
    from app.memory.session import create_session as create_sess
    session = create_sess(user.username, name)
    return {"session": session}


@router.get("/sessions", tags=["会话"])
async def list_sessions(user: UserInfo = Depends(require_user)):
    """列出当前用户的所有会话（按更新时间倒序）"""
    from app.memory.session import list_sessions as list_sess
    sessions = list_sess(user.username)
    return {"sessions": sessions, "total": len(sessions)}


@router.delete("/sessions/{session_id}", tags=["会话"])
async def delete_session(session_id: str, user: UserInfo = Depends(require_user)):
    """删除会话及其所有消息。需为会话所有者。"""
    from app.memory.session import delete_session as delete_sess
    ok = delete_sess(session_id, user.username)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")
    return {"status": "ok", "message": f"会话 {session_id} 已删除"}


@router.patch("/sessions/{session_id}", tags=["会话"])
async def rename_session(
    session_id: str,
    user: UserInfo = Depends(require_user),
    name: str = Query(..., description="新名称"),
):
    """重命名会话。需为会话所有者。"""
    from app.memory.session import rename_session as rename_sess
    ok = rename_sess(session_id, user.username, name)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")
    return {"status": "ok", "session_id": session_id, "name": name}


@router.patch("/sessions/{session_id}/archive", tags=["会话"])
async def toggle_archive_session(
    session_id: str,
    user: UserInfo = Depends(require_user),
    archived: bool = Query(default=True, description="true=归档, false=取消归档"),
):
    """归档/取消归档会话。需为会话所有者。"""
    from app.memory.session import archive_session
    ok = archive_session(session_id, user.username, archived)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")
    return {"status": "ok", "session_id": session_id, "is_archived": archived}


# ─────────────────────────────────────────────────────────────────────────────
# 对话历史
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/chat/history", tags=["对话"])
async def list_conversations(user: UserInfo = Depends(require_user)):
    """列出当前用户的所有会话历史 (从 MySQL + Redis，自动按 user 隔离)"""
    from app.models.database import get_session as get_db, ConversationRecord
    from sqlalchemy import func, desc

    sessions = []
    db = get_db()
    if db:
        try:
            rows = (
                db.query(
                    ConversationRecord.session_id,
                    ConversationRecord.user_id,
                    func.min(ConversationRecord.created_at).label("started"),
                    func.max(ConversationRecord.created_at).label("updated"),
                    func.count().label("messages"),
                    func.substr(func.group_concat(ConversationRecord.content), 1, 100).label("preview"),
                )
                .filter(ConversationRecord.user_id == user.username)
                .group_by(ConversationRecord.session_id, ConversationRecord.user_id)
                .order_by(desc("updated"))
                .limit(50)
                .all()
            )
            for r in rows:
                sessions.append({
                    "session_id": r.session_id,
                    "user_id": r.user_id,
                    "started_at": r.started.isoformat() if r.started else "",
                    "updated_at": r.updated.isoformat() if r.updated else "",
                    "message_count": r.messages,
                    "preview": (r.preview or "")[:100],
                })
        except Exception as e:
            logger.warning(f"MySQL 查询历史失败: {e}")
        finally:
            db.close()

    # 补充 Redis 中的数据
    seen = {s["session_id"] for s in sessions}
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, decode_responses=True)
        for key in r.scan_iter(f"chat:{user.username}:*"):
            parts = key.replace("chat:", "").split(":", 1)
            if len(parts) == 2:
                uid, sid = parts
                if sid not in seen:
                    msgs_raw = r.lrange(key, 0, 0)
                    preview = ""
                    if msgs_raw:
                        try:
                            preview = json.loads(msgs_raw[0]).get("content", "")[:100]
                        except Exception:
                            pass
                    sessions.append({
                        "session_id": sid,
                        "user_id": uid,
                        "started_at": "",
                        "updated_at": "",
                        "message_count": r.llen(key),
                        "preview": preview,
                    })
    except Exception:
        pass

    return {"sessions": sessions, "total": len(sessions)}


@router.get("/chat/history/{session_id}", tags=["对话"])
async def get_conversation(session_id: str, user: UserInfo = Depends(require_user)):
    """获取指定会话的完整消息历史。需为会话所有者。"""
    from app.models.database import get_session as get_db, ConversationRecord

    messages = []
    db = get_db()
    if db:
        try:
            from sqlalchemy import asc
            rows = (
                db.query(ConversationRecord)
                .filter(
                    ConversationRecord.session_id == session_id,
                    ConversationRecord.user_id == user.username,
                )
                .order_by(asc(ConversationRecord.created_at))
                .all()
            )
            for r in rows:
                msg: dict = {
                    "role": r.role,
                    "content": r.content,
                    "time": r.created_at.isoformat() if r.created_at else "",
                }
                meta = r.metadata_json if hasattr(r, 'metadata_json') else None
                if meta and isinstance(meta, dict):
                    msg["metadata"] = meta
                messages.append(msg)
        except Exception as e:
            logger.warning(f"MySQL 查询消息失败: {e}")
        finally:
            db.close()

    # 补充 Redis/内存
    memory = await get_memory_store()
    local = memory.get_history(session_id, user.username)
    if not messages and local:
        messages = [
            {"role": m.role, "content": m.content, "time": m.timestamp.isoformat(),
             **({"metadata": m.metadata} if m.metadata else {})}
            for m in local
        ]

    if not messages:
        from app.memory.session import get_session_owner
        owner = get_session_owner(session_id)
        if owner and owner != user.username:
            raise HTTPException(status_code=403, detail="无权访问该会话")

    return {"session_id": session_id, "messages": messages, "total": len(messages)}


@router.delete("/chat/history/{session_id}", tags=["对话"])
async def delete_conversation(session_id: str, user: UserInfo = Depends(require_user)):
    """删除指定会话。需为会话所有者。"""
    from app.models.database import get_session as get_db, ConversationRecord

    deleted = False
    db = get_db()
    if db:
        try:
            result = db.query(ConversationRecord).filter(
                ConversationRecord.session_id == session_id,
                ConversationRecord.user_id == user.username,
            ).delete()
            db.commit()
            deleted = result > 0
        except Exception as e:
            logger.warning(f"MySQL 删除失败: {e}")
        finally:
            db.close()

    memory = await get_memory_store()
    await memory.clear(session_id, user.username)

    if not deleted:
        from app.memory.session import get_session_owner
        owner = get_session_owner(session_id)
        if owner and owner != user.username:
            raise HTTPException(status_code=403, detail="无权删除该会话")
        if not owner:
            raise HTTPException(status_code=404, detail="会话不存在")

    return {"status": "ok", "message": f"会话 {session_id} 已删除"}
