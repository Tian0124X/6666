"""
AgentState — 2026 Lean State 设计

原则（来自 Kalvium Labs 生产实践）:
- Accumulator: 用 Annotated reducer 的消息/错误/发现列表
- Overwrite: 当前步骤/计数/审批等瞬态字段
- 绝不存原始 LLM 响应或完整文档内容（防 600ms checkpoint 写延迟）

字段生命周期:
- messages: accumulator，checkpoint 自动持久化 → Phase 3 summarizer 激活
- error_count / max_iterations: 预留 → Phase 2 Evaluator-Optimizer 循环边激活
- next_action: 预留 → Phase 2 Supervisor 路由激活
"""

from typing import TypedDict, Annotated, Literal
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    # ====== Accumulators (reducer 追加) ======
    # messages: 对话历史，LangGraph checkpoint 自动持久化
    # TODO Phase 3: summarizer_node 每 N 轮压缩早期消息为摘要
    messages: Annotated[list[BaseMessage], add_messages]
    errors: Annotated[list[str], lambda x, y: (x or []) + (y if isinstance(y, list) else [y])]

    # ====== Overwrites (当前状态) ======
    user_input: str
    task_type: str                          # "simple" | "complex"
    plan_json: str                          # JSON 字符串 (不存 dict 对象)
    sub_results: str                        # JSON 字符串 {"task_id": "result", ...}
    final_answer: str
    # TODO Phase 2: Evaluator-Optimizer 循环边激活 error_count 和 max_iterations
    error_count: int                        # 当前迭代计数 (Evaluator-Optimizer 循环)
    max_iterations: int                     # 最大迭代次数 (默认 3)
    current_step: str                       # 当前正在执行的步骤名
    # TODO Phase 2B: Supervisor 路由激活 next_action
    next_action: str                        # 监督者路由: "simple_react" | "plan" | "execute" | "aggregate" | "FINISH"
