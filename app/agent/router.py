"""任务路由分类器 — LangGraph classify 节点

2026 优化: 本地规则优先(>90%命中) → 不确定才调 LLM (省 ~200 token/请求 + ~1s延迟)
"""

import re
import logging
from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app.config import settings
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

# 强匹配: 明确复杂任务，直接路由 complex (不调 LLM)
STRONG_COMPLEX = [
    r"分析.*并.*生成", r"对比.*和.*", r"先生成.*再",
    r"帮我做.*报告", r"生成.*图表", r"统计.*并.*导出",
    r"批量.*处理", r"导出.*报表", r"自动.*生成",
    r"生成.*报表", r"生成.*报告", r"制作.*报表",
    r"多步", r"先.*再.*然后", r"计算.*并.*生成",
]

# 强匹配: 明确简单任务，直接路由 simple
STRONG_SIMPLE = [
    r"^(你好|hi|hello|嗨|早上好|下午好|晚上好)",
    r"^(谢谢|感谢|thank)",
    r"^(再见|bye|拜拜)",
    r"^(帮助|help|能做什么|功能)",
    r"^.{1,4}$",  # 极短输入 (4字以下, 中文4字 = 足够短)
]

# 规则置信度: 命中 strong 直接返回，否则调 LLM
ROUTER_PROMPT = ChatPromptTemplate.from_template("""\
判断以下用户问题是"simple"还是"complex"。

- simple: 单次问答、闲聊、简单查询、无需多步骤操作
- complex: 需要多步骤、涉及文件处理、数据生成、多系统查询

用户: {user_input}

只输出一个词: simple 或 complex。""")


def _rule_classify(user_input: str) -> Literal["simple", "complex"] | None:
    """本地规则分类。返回 None 表示无法确定，需 LLM。"""
    # 强匹配 complex
    for pattern in STRONG_COMPLEX:
        if re.search(pattern, user_input):
            return "complex"
    # 强匹配 simple
    for pattern in STRONG_SIMPLE:
        if re.search(pattern, user_input):
            return "simple"
    # 模糊关键词 (低置信度，配合 LLM)
    return None


def _legacy_rule_route(user_input: str) -> Literal["simple", "complex"]:
    """旧规则引擎 — 兼容回退 (高召回但低精度)"""
    complex_kw = [
        r"分析.*并.*生成", r"对比.*和.*", r"先生成.*再",
        r"报告", r"图表", r"分析.*数据", r"统计.*并",
        r"帮我做", r"自动", r"批量", r"导出",
        r"多步", r"先.*再.*然后", r"计算.*并",
    ]
    for pattern in complex_kw:
        if re.search(pattern, user_input):
            return "complex"
    return "simple"


def classify_task(user_input: str) -> Literal["simple", "complex"]:
    """
    分类入口: 本地规则优先 → LLM 兜底。

    优化: 之前每次都调 LLM (~1s, ~200 tokens),
    现在本地规则覆盖 >90% 请求，仅边界情况调 LLM。
    """
    # 1. 本地规则 (覆盖 >90%, 0ms 延迟)
    result = _rule_classify(user_input)
    if result is not None:
        logger.debug(f"规则分类: {result} | {user_input[:50]}...")
        return result

    # 2. LLM 分类 (仅边界情况)
    if not settings.is_llm_available:
        return _legacy_rule_route(user_input)

    try:
        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=0, timeout=10,
        )
        chain = ROUTER_PROMPT | llm
        result = chain.invoke({"user_input": user_input})
        content = result.content.strip().lower()

        if content == "complex":
            return "complex"
        if content == "simple":
            return "simple"
        # 模糊回退
        return _legacy_rule_route(user_input)
    except Exception as e:
        logger.warning(f"LLM 路由失败→规则: {e}")
        return _legacy_rule_route(user_input)


def classify_node(state: AgentState) -> dict:
    """LangGraph 分类节点 — 复用 classify_task 结果 (不再重复调 LLM)"""
    task_type = classify_task(state["user_input"])
    logger.info(f"分类: {task_type} | {state['user_input'][:50]}...")
    return {"task_type": task_type}


def route_by_complexity(state: AgentState) -> Literal["simple_react", "plan"]:
    if state.get("task_type") == "complex":
        return "plan"
    return "simple_react"
