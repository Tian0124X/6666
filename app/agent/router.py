"""任务路由分类器 — LangGraph classify 节点"""

import re
import logging
from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app.config import settings
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

COMPLEX_KEYWORDS = [
    r"分析.*并.*生成", r"对比.*和.*", r"先生成.*再",
    r"报告", r"图表", r"分析.*数据", r"统计.*并",
    r"帮我做", r"自动", r"批量", r"导出",
    r"多步", r"先.*再.*然后", r"计算.*并",
]

ROUTER_PROMPT = ChatPromptTemplate.from_template("""\
判断以下用户问题是"simple"还是"complex"。

- simple: 单次问答、闲聊、简单查询、无需多步骤操作
- complex: 需要多步骤、涉及文件处理、数据生成、多系统查询

用户: {user_input}

只输出一个词: simple 或 complex。""")


def rule_route(user_input: str) -> Literal["simple", "complex"]:
    for pattern in COMPLEX_KEYWORDS:
        if re.search(pattern, user_input):
            return "complex"
    return "simple"


def llm_route(user_input: str) -> Literal["simple", "complex"]:
    if not settings.LLM_API_KEY or settings.LLM_API_KEY.startswith("sk-your-"):
        return rule_route(user_input)
    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=0, timeout=10,
    )
    chain = ROUTER_PROMPT | llm
    result = chain.invoke({"user_input": user_input})
    content = result.content.strip().lower()
    # 精确匹配: 只有当 LLM 明确输出 "complex" 时才路由到复杂路径
    # 避免 "not complex"/"might be simple" 等歧义文本被误判
    if content == "complex":
        return "complex"
    if content == "simple":
        return "simple"
    # 模糊回退: 非精确匹配时用规则引擎
    return rule_route(user_input)


def classify_task(user_input: str) -> Literal["simple", "complex"]:
    try:
        return llm_route(user_input)
    except Exception as e:
        logger.warning(f"LLM 路由失败→规则引擎: {e}")
        return rule_route(user_input)


def classify_node(state: AgentState) -> dict:
    """LangGraph 分类节点"""
    task_type = classify_task(state["user_input"])
    logger.info(f"分类: {task_type} | {state['user_input'][:50]}...")
    return {"task_type": task_type}


def route_by_complexity(state: AgentState) -> Literal["simple_react", "plan"]:
    if state.get("task_type") == "complex":
        return "plan"
    return "simple_react"
