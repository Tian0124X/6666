"""结果聚合节点 — 子任务结果 → 自然语言回答"""

import json
import logging
from langchain_openai import ChatOpenAI
from app.config import settings
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

AGGREGATE_PROMPT = """\
你是企业智能办公助手。请将以下子任务执行结果整合成一份完整、清晰的回答。

规则：
1. 如果某子任务失败，在回答中如实说明（不要隐藏错误）
2. 优先呈现成功的结果，失败的任务单独说明
3. 使用 Markdown 格式增强可读性（表格、列表）
4. 对数据分析类结果，突出关键数字和趋势

用户需求：{user_input}

子任务结果：
{results}

请生成最终回答："""


def aggregate_node(state: AgentState) -> dict:
    """LangGraph aggregate 节点"""
    user_input = state["user_input"]
    results_text = "无结果"

    try:
        sub_results = json.loads(state.get("sub_results", "{}"))
        if sub_results:
            lines = []
            for tid, result in sub_results.items():
                lines.append(f"### {tid}\n{result}")
            results_text = "\n\n".join(lines)
    except json.JSONDecodeError:
        results_text = str(state.get("sub_results", "无结果"))

    if not settings.LLM_API_KEY or settings.LLM_API_KEY.startswith("sk-your-"):
        return {"final_answer": f"## 执行结果\n\n{results_text}",
                "current_step": "aggregate_done"}

    try:
        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=0.3, timeout=settings.LLM_TIMEOUT,
        )
        # 使用 safe 模板替换避免用户输入中的 {} 造成 KeyError
        prompt_text = AGGREGATE_PROMPT.replace("{user_input}", user_input).replace("{results}", results_text)
        answer = llm.invoke(prompt_text).content
        return {"final_answer": answer, "current_step": "aggregate_done"}
    except Exception as e:
        logger.error(f"聚合失败: {e}")
        return {"final_answer": f"## 执行结果\n\n{results_text}\n\n⚠️ 结果聚合失败: {e}",
                "current_step": "aggregate_done"}
