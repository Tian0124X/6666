"""任务路由分类器 — LangGraph classify 节点

2026 优化: 复用统一意图识别 (app.agent.intent), 仅做 simple/complex 二分类
"""

import re
import logging
from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app.config import settings
from app.agent.state import AgentState
from app.agent.intent import classify_intent, Intent, is_simple_greeting

logger = logging.getLogger(__name__)

# complex 意图集合 — 这些意图需要多步规划
COMPLEX_INTENTS = {
    Intent.DATA_REPORT,
    Intent.MULTI_DOMAIN,
}

# simple 意图集合 — 这些意图直接回答即可
SIMPLE_INTENTS = {
    Intent.GREETING,
    Intent.GENERAL_CHAT,
    Intent.KNOWLEDGE_QA,
    Intent.OA_QUERY,
    Intent.CRM_QUERY,
    Intent.DATA_ANALYSIS,  # 数据分析通常单轮即可
}

ROUTER_PROMPT = ChatPromptTemplate.from_template("""\
判断以下用户问题是"simple"还是"complex"。

- simple: 单次问答、闲聊、简单查询、无需多步骤操作
- complex: 需要多步骤、涉及文件处理、数据生成、多系统查询

用户: {user_input}

只输出一个词: simple 或 complex。""")


def classify_task(user_input: str) -> Literal["simple", "complex"]:
    """
    分类入口: 统一意图 → simple/complex 二分类。

    复用 app.agent.intent.classify_intent() 的意图识别结果，
    映射到简单/复杂二分类，避免重复维护关键词表。
    """
    # 1. 快速路径: 明确问候/短消息 → simple
    if is_simple_greeting(user_input):
        return "simple"
    if len(user_input.strip()) <= 4:
        return "simple"

    # 2. 意图 → simple/complex 映射
    intent = classify_intent(user_input)

    if intent.primary in COMPLEX_INTENTS or intent.primary == Intent.MULTI_DOMAIN:
        return "complex" if intent.confidence >= 0.5 else "simple"

    if intent.primary in SIMPLE_INTENTS:
        return "simple"

    # 3. 高置信度 data_analysis → 可能 complex（取决于问题复杂度）
    if intent.primary == Intent.DATA_ANALYSIS and intent.confidence >= 0.7:
        # 检查是否有多步骤关键词
        complex_patterns = [
            r"分析.*并.*生成", r"对比.*和.*", r"先生成.*再",
            r"批量", r"导出", r"自动", r"多步",
            r"先.*再.*然后", r"计算.*并",
        ]
        for p in complex_patterns:
            if re.search(p, user_input):
                return "complex"
        return "simple"

    # 4. LLM 兜底 (低置信度边界情况)
    if not settings.is_llm_available:
        return "simple"

    try:
        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=0, timeout=10, max_tokens=50,
        )
        chain = ROUTER_PROMPT | llm
        result = chain.invoke({"user_input": user_input})
        content = result.content.strip().lower()
        return "complex" if content == "complex" else "simple"
    except Exception as e:
        logger.warning(f"LLM 路由失败→simple: {e}")
        return "simple"


def classify_node(state: AgentState) -> dict:
    """LangGraph 分类节点 — 复用 classify_task 结果 (不再重复调 LLM)"""
    task_type = classify_task(state["user_input"])
    logger.info(f"分类: {task_type} | {state['user_input'][:50]}...")
    return {"task_type": task_type}


def route_by_complexity(state: AgentState) -> Literal["simple_react", "plan"]:
    if state.get("task_type") == "complex":
        return "plan"
    return "simple_react"
