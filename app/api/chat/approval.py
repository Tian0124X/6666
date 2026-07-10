"""Human-in-the-Loop 审批端点"""

import logging

from fastapi import APIRouter, HTTPException, Depends

from app.models.user import UserInfo
from app.api.auth import require_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/chat/approvals", tags=["对话"])
async def list_approvals(user: UserInfo = Depends(require_user)):
    """列出当前用户的所有等待审批的操作"""
    from app.agent.human_loop import list_all_pending
    all_pending = list_all_pending()
    user_pending = [
        p for p in all_pending
        if p.get("thread_id", "").startswith(f"{user.username}:")
    ]
    return {"pending": user_pending}


@router.get("/chat/approvals/{thread_id}", tags=["对话"])
async def check_approval(thread_id: str, user: UserInfo = Depends(require_user)):
    """检查是否有待审批操作"""
    from app.agent.human_loop import get_pending
    pending = get_pending(thread_id)
    if pending:
        return {"pending": True, "approval": pending}
    return {"pending": False}


@router.post("/chat/approvals/{thread_id}/approve", tags=["对话"])
async def approve_action(thread_id: str, user: UserInfo = Depends(require_user)):
    """批准操作"""
    from app.agent.human_loop import approve
    ok = approve(thread_id)
    if not ok:
        raise HTTPException(status_code=404, detail="无待审批操作")
    return {"status": "approved"}


@router.post("/chat/approvals/{thread_id}/reject", tags=["对话"])
async def reject_action(
    thread_id: str,
    user: UserInfo = Depends(require_user),
    reason: str = "",
):
    """拒绝操作"""
    from app.agent.human_loop import reject
    ok = reject(thread_id, reason)
    if not ok:
        raise HTTPException(status_code=404, detail="无待审批操作")
    return {"status": "rejected"}
