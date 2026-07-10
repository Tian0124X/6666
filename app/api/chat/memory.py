"""记忆 API — 情景记忆（摘要）+ 语义记忆（事实）"""

import logging

from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel as PydanticModel

from app.models.user import UserInfo
from app.api.auth import require_user

logger = logging.getLogger(__name__)
router = APIRouter()


class FactSearchRequest(PydanticModel):
    query: str = ""
    category: str = ""


@router.get("/memory/facts", tags=["记忆"])
async def get_facts(
    user: UserInfo = Depends(require_user),
    category: str = Query(default=""),
):
    """获取当前用户的记忆事实。可按 category 过滤 (preference/fact/context)。"""
    from app.memory.semantic import get_user_facts
    facts = get_user_facts(user.username, category=category or None)
    return {"facts": facts, "total": len(facts)}


@router.post("/memory/facts/search", tags=["记忆"])
async def search_facts(req: FactSearchRequest, user: UserInfo = Depends(require_user)):
    """搜索用户记忆事实（当前为 MySQL LIKE 匹配，后续可扩展到 pgvector 语义搜索）。"""
    from app.memory.semantic import get_user_facts
    all_facts = get_user_facts(user.username, category=req.category or None)
    if req.query:
        q = req.query.lower()
        all_facts = [f for f in all_facts if q in f["fact"].lower()]
    return {"facts": all_facts, "total": len(all_facts)}


@router.get("/memory/summary/{session_id}", tags=["记忆"])
async def get_session_summary(session_id: str, user: UserInfo = Depends(require_user)):
    """获取指定会话的结构化摘要。"""
    from app.memory.summarizer import get_summary
    summary = get_summary(session_id, user.username)
    if summary:
        return {"summary": summary}
    return {"summary": None}
