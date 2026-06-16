"""
子任务执行器 — DAG 分层并行 + 反思重试

2026 模式: 状态级错误追踪 + 熔断 + Lean State（只存结果 JSON，不存原始对象）
"""

import json
import logging
import asyncio
from langchain_core.tools import BaseTool
from app.agent.state import AgentState
from app.agent.reflection import ReflectionHandler, categorize_error, RETRY_MATRIX, ErrorCategory

logger = logging.getLogger(__name__)


async def execute_single(
    task: dict,
    tool: BaseTool,
    dep_results: dict[str, str],
    reflection: ReflectionHandler,
) -> tuple[str, str, str]:
    """
    执行单个子任务。

    Returns: (task_id, status, result_or_error)
        status: "ok" | "failed" | "fixed"
    """
    task_id = task["task_id"]
    # 兼容 LLM 生成的 "params" 和规则引擎的 "tool_params"
    params = dict(task.get("tool_params") or task.get("params") or {})

    # 注入前置任务结果
    for dep_id in task.get("depends_on", []):
        if dep_id in dep_results:
            params[f"{dep_id}_result"] = dep_results[dep_id]

    try:
        from app.api.monitoring import track_tool_call
        from app.api.analytics import track_event
        track_tool_call(tool.name)
        track_event("tool_call", "system", "", {"tool": tool.name, "task_id": task_id})
        result = await tool.ainvoke(params)
        return task_id, "ok", str(result)
    except Exception as e:
        logger.error(f"子任务 {task_id} 失败: {e}")

        # 判断可重试 (异步指数退避，不阻塞事件循环)
        if not await reflection.can_retry(task_id, e):
            return task_id, "failed", str(e)

        reflection.record_attempt(task_id)

        # LLM 分析修正参数
        fixed_params = await reflection.analyze_and_fix(
            task.get("description", ""), str(e), params,
        )
        if fixed_params:
            try:
                from app.api.monitoring import track_tool_call
                track_tool_call(tool.name)
                result = await tool.ainvoke(fixed_params)
                return task_id, "fixed", str(result)
            except Exception as e2:
                return task_id, "failed", str(e2)

        # 简单重试（超时/网络错误）
        category = categorize_error(e)
        if category in (ErrorCategory.TIMEOUT, ErrorCategory.NETWORK):
            try:
                from app.api.monitoring import track_tool_call
                track_tool_call(tool.name)
                result = await tool.ainvoke(params)
                return task_id, "ok", str(result)
            except Exception as e2:
                return task_id, "failed", str(e2)

        return task_id, "failed", str(e)


async def execute_node(state: AgentState, tools: list[BaseTool]) -> dict:
    """
    LangGraph execute 节点 — 按 execution_order 分层并行。

    2026 Lean State: plan_json 是 JSON 字符串，sub_results 也是。
    """
    import json

    try:
        plan = json.loads(state.get("plan_json", "{}"))
    except json.JSONDecodeError:
        return {"errors": ["plan_json 解析失败"], "sub_results": "{}"}

    execution_order = plan.get("execution_order", [])
    tasks = {t["task_id"]: t for t in plan.get("tasks", [])}
    sub_results: dict[str, str] = {}
    reflection = ReflectionHandler()

    for layer_idx, layer in enumerate(execution_order):
        layer_tasks = []
        for task_id in layer:
            task = tasks.get(task_id)
            if not task:
                continue
            tool_name = task.get("tool_name") or task.get("tool", "")
            tool = next((t for t in tools if t.name == tool_name), None)
            if tool:
                layer_tasks.append(
                    execute_single(task, tool, sub_results, reflection)
                )
            else:
                tool_name = task.get("tool_name") or task.get("tool", "unknown")
                logger.warning(f"工具未注册: {tool_name} (task {task_id})")
                sub_results[task_id] = f"[failed] 工具 '{tool_name}' 未注册"

        if not layer_tasks:
            continue

        results = await asyncio.gather(*layer_tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, tuple):
                tid, status, content = r
                sub_results[tid] = f"[{status}] {content}"
            else:
                logger.error(f"Layer {layer_idx} 执行异常: {r}")

    return {
        "sub_results": json.dumps(sub_results, ensure_ascii=False),
        "current_step": "execute_done",
    }
