"""
多Agent协作引擎 — 借鉴 DATAGEN Supervisor 模式

架构:
  User → Supervisor (分解任务) → [DataAgent, OAAgent, CRMAgent, KnowledgeAgent]
                 ↓ 并行执行
            Aggregator (汇总结果)

使用 LangGraph Send() API 实现动态并行 fan-out。
"""

import json
import logging
from typing import Literal
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from app.config import settings
from app.tools.base import registry

logger = logging.getLogger(__name__)

# ====== Agent 定义 ======

AGENT_DEFINITIONS = {
    "data_agent": {
        "name": "数据分析Agent",
        "role": "📊",
        "description": "处理数据分析、报表生成、Excel/CSV文件操作",
        "tools": ["data_analyzer"],
        "system_prompt": "你是数据分析专家。处理Excel/CSV数据，生成统计摘要、图表和Word报告。",
    },
    "oa_agent": {
        "name": "OA审批Agent",
        "role": "📋",
        "description": "查询OA审批状态、请假/报销/出差申请",
        "tools": ["oa_query"],
        "system_prompt": "你是OA系统专家。查询审批记录、按ID/用户/状态筛选。",
    },
    "crm_agent": {
        "name": "CRM客户Agent",
        "role": "👤",
        "description": "查询CRM客户信息、按行业/等级筛选",
        "tools": ["crm_query"],
        "system_prompt": "你是CRM系统专家。查询客户信息、按行业/等级分类。",
    },
    "knowledge_agent": {
        "name": "知识库Agent",
        "role": "📚",
        "description": "搜索企业知识库、制度文档、FAQ",
        "tools": ["knowledge_search"],
        "system_prompt": "你是企业知识专家。基于知识库文档回答问题，严格引用来源。",
    },
}


# ====== Supervisor ======

SUPERVISOR_PROMPT = """\
你是多Agent协调主管。用户提出复杂需求，你需要:
1. 分析需求涉及哪些子系统
2. 将需求拆解为子任务
3. 分配给最合适的Agent处理
4. 汇总各Agent结果

可用的Agent:
{agents}

输出格式 (严格JSON):
{{"tasks": [
  {{"agent": "data_agent", "task": "分析本月销售数据"}},
  {{"agent": "oa_agent", "task": "查询张三的审批状态"}}
]}}

规则:
- data_agent: 数据分析、报表、Excel
- oa_agent: 审批查询、请假记录
- crm_agent: 客户信息、客户查询
- knowledge_agent: 制度文档、FAQ
- 如果只需要一个Agent，tasks数组只有一项
- 无关联的子任务标记为 parallel
"""


def supervisor_decompose(user_input: str) -> list[dict]:
    """Supervisor: 用 LLM 分解用户需求为子任务"""
    agents_desc = "\n".join(
        f"- {k}: {v['description']}" for k, v in AGENT_DEFINITIONS.items()
    )

    if not settings.is_llm_available:
        # LLM不可用时：用规则分解
        return _rule_decompose(user_input)

    try:
        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=0, timeout=settings.LLM_TIMEOUT,
        )
        response = llm.invoke([
            SystemMessage(content=SUPERVISOR_PROMPT.format(agents=agents_desc)),
            HumanMessage(content=user_input),
        ])
        content = response.content.strip()
        # 清理 JSON
        import re
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        plan = json.loads(content)
        return plan.get("tasks", [])
    except Exception as e:
        logger.warning(f"Supervisor LLM分解失败: {e}")
        return _rule_decompose(user_input)


def _rule_decompose(user_input: str) -> list[dict]:
    """规则引擎分解 (LLM不可用时降级)"""
    tasks = []
    low = user_input.lower()

    if any(kw in low for kw in ["数据", "分析", "报表", "excel", "csv", "图表", "统计"]):
        tasks.append({"agent": "data_agent", "task": user_input})
    if any(kw in low for kw in ["审批", "oa", "请假", "报销", "出差", "加班"]):
        tasks.append({"agent": "oa_agent", "task": user_input})
    if any(kw in low for kw in ["客户", "crm", "公司", "行业", "联系"]):
        tasks.append({"agent": "crm_agent", "task": user_input})
    if any(kw in low for kw in ["制度", "文档", "手册", "规定", "政策", "faq", "年假", "流程", "指南"]):
        tasks.append({"agent": "knowledge_agent", "task": user_input})

    if not tasks:
        tasks.append({"agent": "knowledge_agent", "task": user_input})

    logger.info(f"规则分解: {len(tasks)} 个子任务 → {[t['agent'] for t in tasks]}")
    return tasks


# ====== Agent 执行 ======

def execute_agent_task(agent_name: str, task: str) -> str:
    """执行单个Agent任务 (同步，由 execute_node 在线程池调用)"""
    definition = AGENT_DEFINITIONS.get(agent_name)
    if not definition:
        return f"未知Agent: {agent_name}"

    tools = [t for t in registry.list_tools() if t.name in definition["tools"]]

    if not settings.is_llm_available:
        # 无LLM: 直接调用工具
        if tools:
            try:
                return str(tools[0].invoke({"query": task} if "query" in tools[0].args_schema.model_fields else {}))
            except Exception:
                return f"[{definition['name']}] 无法完成任务: LLM未配置且工具调用失败"
        return f"[{definition['name']}] LLM未配置，请设置API Key"

    try:
        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=0.3, timeout=settings.LLM_TIMEOUT,
        )

        if tools:
            llm_with_tools = llm.bind_tools(tools)
        else:
            llm_with_tools = llm

        messages = [
            SystemMessage(content=definition["system_prompt"]),
            HumanMessage(content=task),
        ]
        response = llm_with_tools.invoke(messages)

        # 工具调用循环 (最多2轮)
        tool_calls = getattr(response, "tool_calls", [])
        for _ in range(2):
            if not tool_calls:
                break
            for tc in tool_calls:
                tool = next((t for t in tools if t.name == tc.get("name", "")), None)
                if tool:
                    try:
                        result = tool.invoke(tc.get("args", {}))
                        from langchain_core.messages import ToolMessage
                        messages.append(response)
                        messages.append(ToolMessage(
                            content=str(result),
                            tool_call_id=tc.get("id", ""),
                        ))
                    except Exception as e:
                        logger.warning(f"工具调用失败: {e}")
            response = llm_with_tools.invoke(messages)
            tool_calls = getattr(response, "tool_calls", [])

        return f"[{definition['role']} {definition['name']}]\n{response.content}"

    except Exception as e:
        logger.error(f"Agent {agent_name} 执行失败: {e}")
        return f"[{definition['name']}] 执行失败: {e}"


# ====== 并行执行入口 ======

def run_multi_agent(user_input: str) -> dict:
    """
    多Agent协作主入口。

    1. Supervisor 分解需求
    2. 各Agent并行执行
    3. 汇总结果

    Returns: {"answer": str, "agents_used": [...], "sub_results": [...]}
    """
    tasks = supervisor_decompose(user_input)
    logger.info(f"Supervisor 分解: {len(tasks)} 任务 → {[t['agent'] for t in tasks]}")

    # 并行执行 (使用线程池并发)
    from concurrent.futures import ThreadPoolExecutor
    results = []
    if len(tasks) > 1:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(execute_agent_task, t["agent"], t["task"]): t
                for t in tasks
            }
            for f in futures:
                t = futures[f]
                try:
                    results.append({
                        "agent": t["agent"],
                        "task": t["task"],
                        "result": f.result(timeout=60),
                    })
                except Exception as e:
                    results.append({
                        "agent": t["agent"],
                        "task": t["task"],
                        "result": f"超时或失败: {e}",
                    })
    else:
        t = tasks[0]
        results.append({
            "agent": t["agent"],
            "task": t["task"],
            "result": execute_agent_task(t["agent"], t["task"]),
        })

    # Aggregator 汇总
    answer = _aggregate_results(user_input, results)
    return {
        "answer": answer,
        "agents_used": [r["agent"] for r in results],
        "sub_results": results,
    }


def _aggregate_results(user_input: str, results: list[dict]) -> str:
    """汇总多个Agent的结果"""
    if not results:
        return "无法完成您的请求。"

    if len(results) == 1:
        return results[0]["result"]

    # 多Agent: LLM 汇总
    parts = "\n\n".join(
        f"### {r['agent']}\n{r['result'][:500]}"
        for r in results
    )

    if not settings.is_llm_available:
        return f"## 多Agent协作结果\n\n{parts}"

    try:
        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=0.3, timeout=settings.LLM_TIMEOUT,
        )
        response = llm.invoke([
            SystemMessage(content="你是多Agent协作汇总专家。将各Agent结果整合为清晰完整的回答，使用Markdown格式。"),
            HumanMessage(content=f"用户需求: {user_input}\n\n各Agent结果:\n{parts}"),
        ])
        return response.content
    except Exception:
        return f"## 多Agent协作结果\n\n{parts}"
