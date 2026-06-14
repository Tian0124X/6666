"""2026 LangGraph Agent 引擎"""

from typing import Optional
from app.agent.state import AgentState


# 懒导入（避免循环依赖）
def get_agent_app():
    from app.agent.graph import get_agent_app as _get
    return _get()


async def run_agent(
    user_input: str,
    thread_id: str = "default",
    history: Optional[list[dict]] = None,
) -> str:
    """运行 Agent 工作流。保持与 graph.run_agent 签名一致。"""
    from app.agent.graph import run_agent as _run
    return await _run(user_input, thread_id=thread_id, history=history)


__all__ = ["AgentState", "get_agent_app", "run_agent"]
