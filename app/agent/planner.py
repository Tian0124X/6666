"""任务规划节点 — LLM 拆解 + 规则降级"""

import json
import logging
from langchain_openai import ChatOpenAI
from app.config import settings
from app.agent.state import AgentState
from app.agent.fallback import rule_based_plan

logger = logging.getLogger(__name__)

PLANNER_PROMPT = """\
你是任务规划专家。将用户需求拆解为子任务步骤。

可用工具：
{tools_description}

规则：
1. 每个子任务必须使用一个可用工具
2. 无数据依赖的子任务可并行（放入同一层）
3. 依赖前置任务输出的子任务放到后续层
4. task_id 格式 "task_N"（N 从 1 开始）

严格按 JSON 输出，不要其他内容：
{{"tasks": [...], "execution_order": [["task_1","task_2"], ["task_3"]]}}"""


def llm_plan(user_input: str, tools_description: str) -> dict:
    if not settings.LLM_API_KEY or settings.LLM_API_KEY.startswith("sk-your-"):
        raise ValueError("LLM 未配置")

    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=0.1, timeout=settings.LLM_TIMEOUT,
    )
    from langchain_core.prompts import ChatPromptTemplate
    prompt = ChatPromptTemplate.from_messages([
        ("system", PLANNER_PROMPT),
        ("user", "用户需求：{user_input}"),
    ])
    chain = prompt | llm
    result = chain.invoke({
        "tools_description": tools_description,
        "user_input": user_input,
    })
    content = result.content.strip()
    # 安全移除 Markdown 代码块标记（正确处理前缀/后缀匹配）
    import re as _re
    content = _re.sub(r'^```(?:json)?\s*', '', content)
    content = _re.sub(r'\s*```$', '', content)
    content = content.strip()
    return json.loads(content)


def plan_node(state: AgentState, tools_description: str) -> dict:
    try:
        plan = llm_plan(state["user_input"], tools_description)
        logger.info(f"LLM 规划: {len(plan.get('tasks',[]))} 个子任务")
        return {"plan_json": json.dumps(plan, ensure_ascii=False)}
    except Exception as e:
        logger.warning(f"LLM 规划失败→规则引擎: {e}")
        return {"plan_json": json.dumps(rule_based_plan(state["user_input"]), ensure_ascii=False)}
