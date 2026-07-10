"""chat 模块共享工具函数 — 历史压缩、记忆钩子、流式输出"""

import json
import logging
from typing import AsyncIterator

from app.config import settings

logger = logging.getLogger(__name__)

# ─── 常量 ───────────────────────────────────────────────────────────────────
MAX_HISTORY_MESSAGES = 6
COMPRESS_AFTER = 8  # 超过 8 条消息触发压缩


# ─── 对话历史智能压缩 ────────────────────────────────────────────────────────
def compress_history(history: list) -> str:
    """
    对话历史智能压缩: 将旧消息总结为一句话摘要。

    优化前: 取最近 6 条原始消息 → 可能 3000+ tokens
    优化后: 旧消息压缩为 1 条摘要 + 最近 4 条原始消息 → ~800 tokens

    Token 节省: ~60-70% (长对话场景)
    """
    recent = history[-MAX_HISTORY_MESSAGES:]
    older = history[:-MAX_HISTORY_MESSAGES] if len(history) > MAX_HISTORY_MESSAGES else []

    if not older:
        return "\n".join(f"[{m.role}]: {m.content[:300]}" for m in history)

    # 长对话: 压缩旧消息
    summary_parts = [f"{m.role}: {m.content[:80]}" for m in older[-4:]]
    summary = " | ".join(summary_parts)

    if settings.is_llm_available and len(older) > 4:
        try:
            from app.rag.llm_factory import get_llm
            from langchain_core.messages import SystemMessage, HumanMessage
            llm = get_llm(temperature=0, timeout=10)
            response = llm.invoke([
                SystemMessage(content="将以下对话历史总结为一句话摘要。只输出摘要。"),
                HumanMessage(content="\n".join(
                    f"{m.role}: {m.content[:200]}" for m in older[-6:]
                )),
            ])
            summary = f"[历史摘要] {response.content.strip()}"
        except Exception:
            summary = f"[历史摘要] {summary}"  # 规则降级

    recent_str = "\n".join(f"[{m.role}]: {m.content[:300]}" for m in recent)
    return f"{summary}\n\n{recent_str}"


# ─── SSE 流式数据输出 ────────────────────────────────────────────────────────
async def stream_data_result(
    result: dict,
    *,
    session_id: str,
    username: str,
    user_message: str,
    route_label: str,
    file_path: str = "",
) -> AsyncIterator[str]:
    """
    统一的 SSE 数据结果输出 — 复用于快速通道和数据通道。

    Yields SSE event strings: data: {...}\n\n
    """
    from app.memory.store import get_memory_store

    answer_text = result.get("answer", "")
    # 按段落拆分发送 (避免截断 markdown 表格/代码块)
    paragraphs = answer_text.split('\n')
    current = ""
    for para in paragraphs:
        current += para + '\n'
        if len(current) >= 200:
            yield f"data: {json.dumps({'content': current}, ensure_ascii=False)}\n\n"
            current = ""
    if current:
        yield f"data: {json.dumps({'content': current}, ensure_ascii=False)}\n\n"

    # 结构化数据 (表格/图表/代码/洞察) — 仅当有实质内容时发送
    code = result.get("code", "")
    r = result.get("result")
    has_result = r and r.get("type") != "error" and r.get("type") is not None
    has_chart = bool(result.get("chart"))
    has_insights = bool(result.get("insights"))

    msg_metadata = None
    if has_result or has_chart or code or has_insights or file_path:
        data_event: dict = {"type": "data_result"}
        if code:
            data_event["code"] = code
        if r and r.get("type") == "dataframe":
            data_event["table"] = {
                "columns": r.get("columns", []),
                "rows": r.get("rows", []),
                "shape": r.get("shape", [0, 0]),
            }
        elif r and r.get("type") == "scalar":
            data_event["scalar"] = r.get("value")
        elif r and r.get("type") == "series":
            data_event["scalar"] = json.dumps(r.get("data", {}), ensure_ascii=False)
        if has_chart:
            data_event["chart"] = result["chart"]
        if has_insights:
            data_event["insights"] = result["insights"]
        suggested = result.get("suggested_questions", [])
        if suggested:
            data_event["suggested_questions"] = suggested
        if file_path:
            data_event["file_path"] = file_path
        yield f"data: {json.dumps(data_event, ensure_ascii=False)}\n\n"
        msg_metadata = {k: v for k, v in data_event.items() if k != "type"}

    yield f"data: {json.dumps({'done': True})}\n\n"

    # 存储对话
    memory = await get_memory_store()
    await memory.add_message(session_id, username, "user", user_message)
    await memory.add_message(session_id, username, "assistant", answer_text, metadata=msg_metadata)

    from app.api.analytics import track_event
    track_event("chat_end", username, session_id, {"has_answer": True, "route": route_label})


# ─── 记忆触发钩子 (内部，非端点) ──────────────────────────────────────────────
async def memory_hooks(session_id: str, user_id: str, messages: list, is_session_end: bool = False):
    """在每次对话交换后调用：触发摘要 + 事实提取"""
    import asyncio

    turn_count = len([m for m in messages if m.role == "user"])
    if not hasattr(messages[0], "role"):
        return  # 不是 ConversationMessage 列表

    # 摘要触发
    try:
        from app.memory.summarizer import should_summarize, generate_summary, generate_final_summary, get_summary
        existing = get_summary(session_id, user_id)
        prev_turns = existing.get("turn_count", 0) if existing else 0

        if is_session_end and turn_count > 4:
            await asyncio.to_thread(generate_final_summary, session_id, user_id, messages)
        elif should_summarize(turn_count) and turn_count > prev_turns:
            await asyncio.to_thread(generate_summary, session_id, user_id, messages)
    except Exception as e:
        logger.debug(f"摘要钩子跳过: {e}")

    # 事实提取
    try:
        from app.memory.semantic import extract_facts
        await asyncio.to_thread(extract_facts, user_id, messages)
    except Exception as e:
        logger.debug(f"事实提取钩子跳过: {e}")
