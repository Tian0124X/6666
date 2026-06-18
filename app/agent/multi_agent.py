"""
多Agent协作引擎 — 借鉴 DATAGEN Supervisor 模式

架构:
  User → Supervisor (本地规则优先→LLM兜底) → [Agents并行]
                 ↓ asyncio.gather (真异步)
            Aggregator (单Agent直返, 多Agent LLM汇总)

2026 优化:
  - 本地关键词分解覆盖 >90% 场景，省 Supervisor LLM 调用
  - ThreadPoolExecutor → asyncio.gather (真异步)
  - 单 Agent 结果直接返回，跳过 LLM 汇总
"""

import json
import asyncio
import logging
from typing import Literal
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
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

# ====== 本地关键词分解规则 (覆盖 >90% 场景，零延迟) ======

KEYWORD_AGENT_MAP: list[tuple[list[str], str]] = [
    (["数据", "分析", "报表", "excel", "csv", "图表", "统计", "趋势", "销量"], "data_agent"),
    (["审批", "oa", "请假", "报销", "出差", "加班", "申请"], "oa_agent"),
    (["客户", "crm", "行业", "联系", "线索", "商机"], "crm_agent"),
    (["制度", "文档", "手册", "规定", "政策", "faq", "年假", "流程", "指南", "怎么", "如何"], "knowledge_agent"),
]


def _rule_decompose(user_input: str) -> list[dict]:
    """本地规则分解 — 零延迟，覆盖 >90% 场景"""
    low = user_input.lower()
    tasks = []
    seen_agents = set()

    for keywords, agent in KEYWORD_AGENT_MAP:
        if agent in seen_agents:
            continue
        if any(kw in low for kw in keywords):
            tasks.append({"agent": agent, "task": user_input})
            seen_agents.add(agent)

    if not tasks:
        tasks.append({"agent": "knowledge_agent", "task": user_input})

    logger.info(f"规则分解: {len(tasks)} 任务 → {[t['agent'] for t in tasks]}")
    return tasks


# ====== Supervisor (LLM 兜底) ======

SUPERVISOR_PROMPT = """\
你是多Agent协调主管。分析需求并分配给合适的Agent。

可用的Agent:
{agents}

输出格式 (严格JSON):
{{"tasks": [{{"agent": "data_agent", "task": "具体任务描述"}}]}}

规则:
- data_agent: 数据分析、报表、Excel
- oa_agent: 审批查询、请假记录
- crm_agent: 客户信息、客户查询
- knowledge_agent: 制度文档、FAQ
- 无关联子任务可并行
"""


def _llm_decompose(user_input: str) -> list[dict]:
    """LLM 分解 — 仅本地规则无法覆盖时使用"""
    agents_desc = "\n".join(
        f"- {k}: {v['description']}" for k, v in AGENT_DEFINITIONS.items()
    )

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
        import re
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        plan = json.loads(content)
        tasks = plan.get("tasks", [])
        # LLM 也失败 → 规则兜底
        return tasks if tasks else _rule_decompose(user_input)
    except Exception as e:
        logger.warning(f"LLM分解失败→规则: {e}")
        return _rule_decompose(user_input)


def supervisor_decompose(user_input: str) -> list[dict]:
    """
    Supervisor: 本地规则优先 (>90% 命中, 0ms) → LLM 兜底。

    只有输入同时匹配多类关键词或完全不匹配时才调 LLM。
    """
    # 1. 本地规则
    rule_tasks = _rule_decompose(user_input)

    # 2. 是否需要 LLM 精炼？
    #    规则已覆盖的情况直接返回；边界情况 (0 个匹配 或 >=3 个匹配) 用 LLM
    if len(rule_tasks) >= 3 or (len(rule_tasks) == 1 and rule_tasks[0]["agent"] == "knowledge_agent"):
        # 边界情况: 多系统或全匹配知识库 → LLM 确认
        if settings.is_llm_available:
            logger.debug("边界情况，LLM确认分解...")
            return _llm_decompose(user_input)

    return rule_tasks


# ====== Agent 执行 (异步) ======

async def _execute_agent_async(agent_name: str, task: str) -> str:
    """异步执行单个 Agent 任务"""
    definition = AGENT_DEFINITIONS.get(agent_name)
    if not definition:
        return f"未知Agent: {agent_name}"

    tools = [t for t in registry.list_tools() if t.name in definition["tools"]]

    if not settings.is_llm_available:
        if tools:
            try:
                return str(tools[0].invoke({"query": task} if "query" in tools[0].args_schema.model_fields else {}))
            except Exception:
                return f"[{definition['name']}] 无法完成任务: LLM未配置且工具调用失败"
        return f"[{definition['name']}] LLM未配置"

    try:
        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=0.3, timeout=settings.LLM_TIMEOUT,
        )

        llm_with_tools = llm.bind_tools(tools) if tools else llm
        messages = [
            SystemMessage(content=definition["system_prompt"]),
            HumanMessage(content=task),
        ]
        response = await llm_with_tools.ainvoke(messages)
        messages.append(response)

        # 工具调用循环 (最多2轮)
        tool_calls = getattr(response, "tool_calls", [])
        for _ in range(2):
            if not tool_calls:
                break
            for tc in tool_calls:
                tool = next((t for t in tools if t.name == tc.get("name", "")), None)
                if tool:
                    try:
                        result = await tool.ainvoke(tc.get("args", {}))
                        messages.append(ToolMessage(
                            content=str(result),
                            tool_call_id=tc.get("id", ""),
                        ))
                    except Exception as e:
                        logger.warning(f"工具调用失败: {e}")
            response = await llm_with_tools.ainvoke(messages)
            tool_calls = getattr(response, "tool_calls", [])

        return f"[{definition['role']} {definition['name']}]\n{response.content}"

    except Exception as e:
        logger.error(f"Agent {agent_name} 执行失败: {e}")
        return f"[{definition['name']}] 执行失败: {e}"


# ====== 并行执行入口 ======

def run_multi_agent(user_input: str) -> dict:
    """
    多Agent协作主入口 — 异步并行。

    1. Supervisor 分解 (规则优先)
    2. asyncio.gather 并行执行 (真异步)
    3. 汇总 (单Agent直返, 多Agent LLM汇总)
    """
    tasks = supervisor_decompose(user_input)
    logger.info(f"Supervisor 分解: {len(tasks)} 任务 → {[t['agent'] for t in tasks]}")

    # 并行执行 (asyncio.gather — 真异步, 不占用线程池)
    async def _run_all():
        return await asyncio.gather(
            *[_execute_agent_async(t["agent"], t["task"]) for t in tasks],
            return_exceptions=True,
        )

    try:
        loop = asyncio.get_running_loop()
        # 已有事件循环: 用线程池跑 asyncio.run (兼容同步上下文)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _run_all())
            agent_results = future.result(timeout=60)
    except RuntimeError:
        # 无事件循环: 直接 asyncio.run
        agent_results = asyncio.run(_run_all())

    # 组装结果
    results = []
    for i, r in enumerate(agent_results):
        t = tasks[i]
        if isinstance(r, Exception):
            results.append({"agent": t["agent"], "task": t["task"], "result": f"执行失败: {r}"})
        else:
            results.append({"agent": t["agent"], "task": t["task"], "result": str(r)})

    # 汇总
    answer = _aggregate_results(user_input, results)
    return {
        "answer": answer,
        "agents_used": [r["agent"] for r in results],
        "sub_results": results,
    }


def _aggregate_results(user_input: str, results: list[dict]) -> str:
    """
    汇总 Agent 结果。

    优化:
    - 单 Agent → 直接返回结果 (省 LLM 汇总调用)
    - 多 Agent → LLM 汇总整合
    """
    if not results:
        return "无法完成您的请求。"

    # 单 Agent: 直接返回
    if len(results) == 1:
        return results[0]["result"]

    # 多 Agent: 拼接预览
    parts = "\n\n".join(
        f"### {r['agent']}\n{r['result'][:300]}"
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
            SystemMessage(content="你是多Agent协作汇总专家。将各Agent结果整合为清晰完整的回答，使用Markdown格式。不要重复原始数据，只整合关键结论。"),
            HumanMessage(content=f"用户需求: {user_input}\n\n各Agent结果:\n{parts}"),
        ])
        return response.content
    except Exception:
        return f"## 多Agent协作结果\n\n{parts}"
