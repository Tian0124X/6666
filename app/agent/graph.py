"""
LangGraph 工作流组装 — 2026 生产模式

参考:
  - LangGraph + MCP 2026 Guide (StateGraph supervisor pattern)
  - Kalvium Labs (lean state, iteration guard, deterministic routing)
  - deep-research-agent (circuit breaker, checkpointing)

Graph 结构:
  entry → classify ──(simple)──▶ simple_react ──▶ END
                    └─(complex)─▶ plan ──▶ execute ──▶ aggregate ──▶ END

编码原则:
  1. 纯函数路由 (不调用 LLM 做路由决策)
  2. Lean State (只存 JSON 字符串，不存对象)
  3. 迭代保护 (error_count, max_iterations)
  4. SqliteSaver 持久化 (生产) / MemorySaver (开发)
"""

import json
import logging
from typing import Literal, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.tools import BaseTool
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

from app.agent.state import AgentState
from app.agent.router import classify_node, route_by_complexity
from app.agent.planner import plan_node
from app.agent.executor import execute_node
from app.agent.aggregator import aggregate_node
from app.tools.base import registry
from app.config import settings

logger = logging.getLogger(__name__)

# 全局 Graph 实例 (懒加载)
_agent_app = None


def _simple_react_node(state: AgentState, tools: list[BaseTool]) -> dict:
    """简单问答节点 — bind_tools 实现真正的工具调用 (langchain 1.x)"""
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage

    # 使用 state["messages"] 获取完整对话历史
    messages = list(state.get("messages", []))
    user_input = state["user_input"]

    SYSTEM_PROMPT = """你是企业智能办公助手。根据用户需求，你可以直接回答，也可以调用工具获取数据。

工具使用原则：
- 用户问数据分析 → 调用 data_analyzer
- 用户问审批/报销 → 调用 oa_query
- 用户问客户信息 → 调用 crm_query
- 用户问公司制度/文档 → 调用 knowledge_search
- 简单闲聊直接回答，不需要调用工具
- 调用工具后根据返回结果总结回答"""

    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=0.5, timeout=settings.LLM_TIMEOUT,
    )

    # bind_tools 让 LLM 自动决定是否调用工具
    if tools:
        llm_with_tools = llm.bind_tools(tools)
    else:
        llm_with_tools = llm

    # 构建消息: 系统提示 + 历史 + 当前输入
    invoke_messages = [SystemMessage(content=SYSTEM_PROMPT)]
    if messages:
        # 取最近 10 条历史消息
        invoke_messages.extend(messages[-10:])
    else:
        invoke_messages.append(HumanMessage(content=user_input))

    # 工具调用循环 (最多 5 轮)
    max_rounds = 5
    for _ in range(max_rounds):
        response = llm_with_tools.invoke(invoke_messages)
        invoke_messages.append(response)

        # 检查是否有工具调用
        tool_calls = getattr(response, "tool_calls", [])
        if not tool_calls:
            # 无工具调用 → 返回最终回答
            return {"final_answer": response.content or ""}

        # 执行工具调用
        for tc in tool_calls:
            tool_name = tc.get("name", "")
            tool_args = tc.get("args", {})
            tool = next((t for t in tools if t.name == tool_name), None)
            if tool:
                try:
                    result = tool.invoke(tool_args)
                    invoke_messages.append(ToolMessage(
                        content=str(result),
                        tool_call_id=tc.get("id", ""),
                    ))
                except Exception as e:
                    invoke_messages.append(ToolMessage(
                        content=f"工具调用失败: {e}",
                        tool_call_id=tc.get("id", ""),
                    ))
            else:
                invoke_messages.append(ToolMessage(
                    content=f"工具 '{tool_name}' 未注册",
                    tool_call_id=tc.get("id", ""),
                ))

    # 达到最大轮数，让 LLM 总结
    final = llm.invoke(invoke_messages)
    return {"final_answer": final.content or ""}


def create_agent_graph(tools: list[BaseTool] | None = None):
    """创建并编译 LangGraph 工作流"""
    if tools is None:
        tools = registry.list_tools()
    tools_desc = registry.get_tools_description()

    workflow = StateGraph(AgentState)

    # 注册节点
    workflow.add_node("classify", classify_node)
    workflow.add_node(
        "simple_react",
        lambda s: _simple_react_node(s, tools),
    )
    workflow.add_node(
        "plan",
        lambda s: plan_node(s, tools_desc),
    )
    async def _execute_wrapper(s: AgentState) -> dict:
        return await execute_node(s, tools)

    workflow.add_node("execute", _execute_wrapper)
    workflow.add_node("aggregate", aggregate_node)

    # 入口
    workflow.set_entry_point("classify")

    # 条件边 — 纯函数路由 (2026: 不做 LLM 路由决策)
    workflow.add_conditional_edges(
        "classify", route_by_complexity,
        {"simple_react": "simple_react", "plan": "plan"},
    )

    # 普通边
    workflow.add_edge("simple_react", END)
    workflow.add_edge("plan", "execute")
    workflow.add_edge("execute", "aggregate")
    workflow.add_edge("aggregate", END)

    # 编译 — SqliteSaver (持久化) / MemorySaver (降级)
    # 会话 checkpoint 持久化到 SQLite，服务重启不丢失对话上下文
    try:
        import os
        import sqlite3
        from langgraph.checkpoint.sqlite import SqliteSaver
        os.makedirs("data", exist_ok=True)
        conn = sqlite3.connect("data/checkpoints.db", check_same_thread=False)
        checkpointer = SqliteSaver(conn)
        logger.info("Checkpointer: SqliteSaver (持久化 → data/checkpoints.db)")
    except Exception as e:
        logger.warning(f"SqliteSaver 不可用，降级 MemorySaver: {e}")
        checkpointer = MemorySaver()
        logger.info("Checkpointer: MemorySaver (内存)")

    app = workflow.compile(checkpointer=checkpointer)
    logger.info("LangGraph 工作流编译完成")
    return app


def get_agent_app() -> StateGraph:
    global _agent_app
    if _agent_app is None:
        _agent_app = create_agent_graph()
    return _agent_app


def _dict_to_messages(history: list[dict]) -> list[BaseMessage]:
    """将前端传来的 dict 列表转为 LangChain 消息对象。"""
    messages = []
    for entry in history:
        role = entry.get("role", "")
        content = entry.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages


async def run_agent(
    user_input: str,
    thread_id: str = "default",
    history: Optional[list[dict]] = None,
) -> str:
    """
    运行 Agent 工作流主入口。

    Args:
        user_input: 用户输入
        thread_id: 会话线程 ID (checkpoint 隔离 & 多用户)
        history: 可选的历史对话 [{"role":"user","content":"..."}, ...]
                 传入后作为 messages accumulator 的初始值，
                 LangGraph checkpoint 会自动追加新消息。

    Returns:
        最终回答文本
    """
    import asyncio
    app = get_agent_app()
    config = {"configurable": {"thread_id": thread_id}}

    # 初始消息列表: 历史消息 + 当前用户输入
    init_messages: list[BaseMessage] = []
    if history:
        init_messages = _dict_to_messages(history)
    init_messages.append(HumanMessage(content=user_input))

    initial: AgentState = {
        "messages": init_messages,
        "errors": [],
        "user_input": user_input,
        "task_type": "",
        "plan_json": "{}",
        "sub_results": "{}",
        "final_answer": "",
        "error_count": 0,
        "max_iterations": 3,
        "current_step": "entry",
        "next_action": "",
    }

    try:
        final_state = await app.ainvoke(initial, config)
        return final_state.get("final_answer", "抱歉，处理失败。")
    except Exception as e:
        logger.error(f"Agent 执行异常: {e}", exc_info=True)
        return f"处理过程中出现错误: {e}"


def visualize_graph(output_path: str = "docs/agent_graph.txt"):
    """导出 Mermaid 图 (在线渲染: https://mermaid.live)"""
    app = get_agent_app()
    try:
        mermaid = app.get_graph().draw_mermaid()
        import os; os.makedirs("docs", exist_ok=True)
        with open(output_path, "w") as f:
            f.write(mermaid)
        logger.info(f"Graph 图已保存: {output_path}")
    except Exception as e:
        logger.warning(f"可视化失败: {e}")


if __name__ == "__main__":
    # 本地调试
    import asyncio
    app = create_agent_graph()
    visualize_graph()
    result = asyncio.run(run_agent("你好，请介绍一下你能做什么"))
    print(result)
