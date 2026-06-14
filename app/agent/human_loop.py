"""
Human-in-the-Loop — 借鉴 DATAGEN 的 interrupt() 模式

敏感操作 (文件删除/代码执行/外部API) 前暂停 Agent，等待人工审批。
LangGraph interrupt() + Command(resume=...) 实现。
"""

import logging
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# ====== 审批队列 (内存，生产可换 Redis) ======

@dataclass
class PendingApproval:
    thread_id: str
    action: str          # "delete_file" | "run_code" | "external_api" | "modify_config"
    description: str     # 人工可读的操作说明
    details: dict        # 操作参数详情
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

_pending: dict[str, PendingApproval] = {}    # thread_id → approval
_decisions: dict[str, bool] = {}              # thread_id → approved/rejected


def request_approval(thread_id: str, action: str, description: str, details: dict) -> bool:
    """
    请求人工审批。阻塞直到用户做出决定。
    返回 True = 批准, False = 拒绝。

    用法 (Agent 节点内):
        approved = request_approval(config["thread_id"], "delete_file", ...)
        if not approved:
            return {"final_answer": "操作已被用户拒绝。"}
    """
    approval = PendingApproval(
        thread_id=thread_id,
        action=action,
        description=description,
        details=details,
    )
    _pending[thread_id] = approval
    logger.info(f"🔔 等待审批: [{action}] {description} (thread={thread_id})")

    # 这里简化: 同步等待最多 120 秒
    # 生产环境用 LangGraph interrupt() + asyncio.Event
    import time
    waited = 0
    while thread_id not in _decisions and waited < 120:
        time.sleep(1)
        waited += 1

    decision = _decisions.pop(thread_id, None)
    _pending.pop(thread_id, None)

    if decision is None:
        logger.warning(f"审批超时 → 自动拒绝: {thread_id}")
        return False
    return decision


def approve(thread_id: str) -> bool:
    """批准操作"""
    if thread_id in _pending:
        _decisions[thread_id] = True
        logger.info(f"✅ 已批准: {thread_id}")
        return True
    return False


def reject(thread_id: str, reason: str = "") -> bool:
    """拒绝操作"""
    if thread_id in _pending:
        _decisions[thread_id] = False
        logger.info(f"❌ 已拒绝: {thread_id} ({reason})")
        return True
    return False


def get_pending(thread_id: str) -> Optional[dict]:
    """查询是否有待审批的操作"""
    a = _pending.get(thread_id)
    if a:
        return {
            "thread_id": a.thread_id,
            "action": a.action,
            "description": a.description,
            "details": a.details,
            "created_at": a.created_at,
        }
    return None


def list_all_pending() -> list[dict]:
    """列出所有待审批"""
    return [
        {
            "thread_id": a.thread_id,
            "action": a.action,
            "description": a.description,
            "details": a.details,
            "created_at": a.created_at,
        }
        for a in _pending.values()
    ]


# ====== 敏感操作检测规则 ======

SENSITIVE_PATTERNS = {
    "delete_file": ["删除文件", "delete file", "rm ", "os.remove", "unlink"],
    "run_code": ["执行代码", "exec(", "eval(", "subprocess", "os.system"],
    "external_api": ["发送到外部", "调用外部API", "付费", "扣款"],
    "modify_config": ["修改配置", "更改设置", "重启服务", "关闭服务"],
}

def is_sensitive(action_str: str) -> Optional[str]:
    """检测操作是否敏感，返回敏感类型"""
    for category, patterns in SENSITIVE_PATTERNS.items():
        for pat in patterns:
            if pat in action_str:
                return category
    return None
