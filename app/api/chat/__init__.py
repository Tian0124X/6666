"""chat API 包 — 聚合所有子模块路由

拆分结构:
    _helpers.py   共享工具（历史压缩、记忆钩子、流式输出）
    core.py       POST /chat  +  POST /chat/stream
    sessions.py   会话 CRUD + 对话历史
    approval.py   Human-in-the-Loop 审批
    media.py      图片分析 + 报告下载
    memory.py     情景/语义记忆 API

main.py 通过 `from app.api import chat; app.include_router(chat.router, prefix="/api")`
引用统一导出的 router。
"""

from fastapi import APIRouter

from .core import router as core_router
from .sessions import router as sessions_router
from .approval import router as approval_router
from .media import router as media_router
from .memory import router as memory_router

router = APIRouter()

router.include_router(core_router)
router.include_router(sessions_router)
router.include_router(approval_router)
router.include_router(media_router)
router.include_router(memory_router)
