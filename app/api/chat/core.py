"""对话核心端点 — POST /chat + POST /chat/stream"""

import json
import os
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.config import settings
from app.models.request import ChatRequest
from app.models.response import ChatResponse
from app.agent.graph import run_agent
from app.agent.router import classify_task
from app.agent.intent import Intent
from app.memory.store import get_memory_store
from app.models.user import UserInfo
from app.api.auth import require_user

from . import _helpers as H

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# POST /chat  (非流式)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/chat", response_model=ChatResponse, tags=["对话"])
async def chat(req: ChatRequest, user: UserInfo = Depends(require_user)):
    """
    对话接口 — 自动路由简单/复杂任务，调用 LangGraph Agent 引擎。
    需要登录。user_id 从 Bearer token 推导，忽略请求体中的 user_id。
    """
    try:
        memory = await get_memory_store()
        history = memory.get_history(req.session_id, user.username)

        if history:
            context = H.compress_history(history)
            full_input = f"对话历史：\n{context}\n\n用户最新问题：{req.message}"
        else:
            full_input = req.message

        task_type = classify_task(full_input) or "simple"
        thread_id = f"{user.username}:{req.session_id}"
        agents_used = []

        if task_type == "complex":
            try:
                import asyncio as _asyncio
                from app.agent.multi_agent import run_multi_agent
                multi_result = await _asyncio.to_thread(run_multi_agent, full_input)
                answer = multi_result["answer"]
                agents_used = multi_result.get("agents_used", [])
            except Exception as e:
                logger.warning(f"多Agent协作失败，降级标准Agent: {e}")
                answer = await run_agent(full_input, thread_id=thread_id)
        else:
            answer = await run_agent(full_input, thread_id=thread_id)

        await memory.add_message(req.session_id, user.username, "user", req.message)
        await memory.add_message(req.session_id, user.username, "assistant", answer)

        return ChatResponse(answer=answer, task_type=task_type)
    except Exception as e:
        logger.error(f"对话处理失败: {e}", exc_info=True)
        return ChatResponse(answer=f"处理过程中出现错误: {str(e)}", task_type="simple")


# ─────────────────────────────────────────────────────────────────────────────
# POST /chat/stream  (SSE 流式)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/chat/stream", tags=["对话"])
async def chat_stream(req: ChatRequest, user: UserInfo = Depends(require_user)):
    """
    流式对话 — SSE 实时推送，通过 LangGraph Agent 引擎。
    使用 LangGraph astream_events() 获取 token 级流式输出。
    """
    from app.agent.graph import get_agent_app
    from app.agent.state import AgentState
    from langchain_core.messages import HumanMessage

    async def event_generator():
        memory = await get_memory_store()

        # ====== 统一意图路由 ======
        from app.agent.intent import classify_intent, Intent, extract_file_path

        file_path = extract_file_path(req.message)
        has_file = bool(file_path)
        intent = classify_intent(req.message, has_file=has_file)

        logger.info(
            f"意图路由: {intent.primary.value} conf={intent.confidence} "
            f"has_file={has_file} user={user.username} | {req.message[:60]}..."
        )

        # ─── 数据对话通道 ─────────────────────────────────────────────────────
        if intent.primary in (Intent.DATA_ANALYSIS, Intent.DATA_REPORT):
            async for chunk in _handle_data_channel(req, user, memory, intent, file_path):
                yield chunk
            return

        # ─── RAG 快速通道 ─────────────────────────────────────────────────────
        if (
            intent.primary == Intent.KNOWLEDGE_QA
            and intent.confidence >= 0.85
            and settings.RAG_KNOWLEDGE_FAST_CHANNEL
        ):
            consumed = False
            async for chunk in _handle_rag_fast_channel(req, user, memory):
                consumed = True
                yield chunk
            if consumed:
                return
            # RAG 失败 → 继续走 Agent 通道

        # ─── 标准 Agent 通道 ──────────────────────────────────────────────────
        async for chunk in _handle_agent_channel(req, user, memory):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 内部通道处理函数
# ─────────────────────────────────────────────────────────────────────────────


async def _handle_data_channel(req, user, memory, intent, file_path):
    """数据对话通道 — 处理数据分析/报告意图"""
    import asyncio
    import re as _re
    from app.tools.data_conversation import analyze_with_llm

    if file_path:
        target_file = file_path
        user_question = _re.sub(
            r'\[已上传数据文件:\s*[^\]]+\]\s*', '', req.message
        ).replace('用户问题:', '').strip()
        route_label = "data_fast"
    else:
        demo = "data/documents/商品数据明细_豆包AI生成.xlsx"
        if os.path.exists(demo):
            target_file = demo
            user_question = req.message
            route_label = "data_fallback"
            yield f"data: {json.dumps({'status': '未检测到上传文件，正在使用示例数据...'}, ensure_ascii=False)}\n\n"
        else:
            yield f"data: {json.dumps({'content': '请先上传 Excel/CSV 数据文件再提问。点击输入框左侧的 📊 按钮上传。'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
            return

    logger.info(f"数据通道: file={target_file}, question={user_question[:80]}")
    yield f"data: {json.dumps({'status': '正在分析数据...'}, ensure_ascii=False)}\n\n"

    try:
        result = await asyncio.to_thread(analyze_with_llm, target_file, user_question, req.with_chart)
    except Exception as e:
        logger.error(f"数据分析失败: {e}", exc_info=True)
        yield f"data: {json.dumps({'content': f'数据分析失败: {e}'}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
        return

    async for chunk in H.stream_data_result(
        result,
        session_id=req.session_id,
        username=user.username,
        user_message=req.message,
        route_label=route_label,
        file_path=target_file,
    ):
        yield chunk

    # data_report 意图自动触发报告生成
    if intent.primary == Intent.DATA_REPORT and target_file:
        try:
            from app.tools.data_conversation import generate_data_report
            report_path = await asyncio.to_thread(generate_data_report, target_file)
            if os.path.exists(report_path):
                report_url = f"/api/chat/report/generate?file_path={target_file}"
                yield f"data: {json.dumps({'content': '\n\n---\n✅ 分析报告已生成！点击下方按钮下载 Word 文档。', 'report_url': report_url}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"自动报告生成失败: {e}", exc_info=True)
            yield f"data: {json.dumps({'content': f'\n\n⚠️ 报告生成失败: {e}'}, ensure_ascii=False)}\n\n"


async def _handle_rag_fast_channel(req, user, memory):
    """RAG 快速通道 — 高置信度知识问题直调 smart_rag_qa。

    异步生成器：成功时 yield SSE 片段，失败时 yield 0 个片段（调用方据此降级 Agent）。
    """
    from app.rag.advanced import smart_rag_qa

    try:
        history = memory.get_history(req.session_id, user.username)
        rag_query = req.message
        if history:
            recent = history[-6:]
            ctx_lines = [f"{m.role}: {m.content}" for m in recent]
            context = "\n".join(ctx_lines)
            rag_query = f"对话历史：\n{context}\n\n用户最新问题：{req.message}"

        rag_result = await smart_rag_qa(rag_query)
        rag_answer = rag_result.get("answer", "")

        # 成功后才推送状态（避免失败时出现悬空提示）
        yield f"data: {json.dumps({'status': '📚 检索知识库完成'}, ensure_ascii=False)}\n\n"

        for para in rag_answer.split('\n'):
            if para.strip():
                yield f"data: {json.dumps({'content': para + chr(10)}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'knowledge_result', 'sources': rag_result.get('sources', []), 'mode': rag_result.get('mode', 'standard'), 'level': rag_result.get('level', -1), 'from_cache': rag_result.get('from_cache', False)}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

        await memory.add_message(req.session_id, user.username, "user", req.message)
        await memory.add_message(req.session_id, user.username, "assistant", rag_answer)

        from app.api.analytics import track_event
        track_event("chat_end", user.username, req.session_id, {"has_answer": True, "route": "rag_fast"})

    except Exception as e:
        logger.warning(f"RAG 快速通道失败，降级 Agent: {e}")
        # 不 yield 任何内容 → 调用方 consumed=False → 降级 Agent


async def _handle_agent_channel(req, user, memory):
    """标准 Agent 通道 — 流式 SSE 推送"""
    import asyncio as _asyncio
    from app.agent.graph import get_agent_app
    from app.agent.state import AgentState
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage as LCMessage

    history = memory.get_history(req.session_id, user.username)

    # 注入用户画像
    from app.memory.semantic import inject_facts_to_prompt
    user_profile = inject_facts_to_prompt(user.username)

    msgs: list = []
    if history and len(history) > H.COMPRESS_AFTER:
        compressed = H.compress_history(history)
        system_text = f"对话历史摘要: {compressed}"
        if user_profile:
            system_text = user_profile + "\n\n" + system_text
        msgs.append(LCMessage(content=system_text))
        for m in history[-4:]:
            if m.role == "user":
                msgs.append(HumanMessage(content=m.content))
            elif m.role == "assistant":
                msgs.append(AIMessage(content=m.content))
    elif history:
        if user_profile:
            msgs.append(LCMessage(content=user_profile))
        for m in history[-H.MAX_HISTORY_MESSAGES:]:
            if m.role == "user":
                msgs.append(HumanMessage(content=m.content))
            elif m.role == "assistant":
                msgs.append(AIMessage(content=m.content))
    elif user_profile:
        msgs.append(LCMessage(content=user_profile))

    msgs.append(HumanMessage(content=req.message))

    from app.api.analytics import track_event
    track_event("chat_start", user.username, req.session_id)

    full_answer = ""
    try:
        app = get_agent_app()
        thread_id = f"{user.username}:{req.session_id}"
        config = {"configurable": {"thread_id": thread_id}}

        initial: AgentState = {
            "messages": msgs,
            "errors": [],
            "user_input": req.message,
            "task_type": "",
            "plan_json": "{}",
            "sub_results": "{}",
            "final_answer": "",
            "error_count": 0,
            "max_iterations": 3,
            "current_step": "entry",
            "next_action": "",
        }

        total_tokens = 0
        async for event in app.astream_events(initial, config, version="v2"):
            kind = event.get("event", "")
            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    full_answer += chunk.content
                    yield f"data: {json.dumps({'content': chunk.content}, ensure_ascii=False)}\n\n"
                if chunk and hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                    total_tokens = chunk.usage_metadata.get("total_tokens", total_tokens)
            elif kind == "on_custom_event":
                name = event.get("name", "")
                if name == "tool_start":
                    tool_name = event.get("data", {}).get("name", "")
                    from app.api.monitoring import track_tool_call
                    track_tool_call(tool_name)
                    yield f"data: {json.dumps({'status': f'🔧 调用工具: {tool_name}...'}, ensure_ascii=False)}\n\n"

        if total_tokens > 0:
            from app.api.monitoring import track_token_usage
            track_token_usage(total_tokens)

        # 降级：无流式输出时直接调用
        if not full_answer:
            result = await app.ainvoke(initial, config)
            full_answer = result.get("final_answer", "抱歉，处理失败。")
            yield f"data: {json.dumps({'content': full_answer}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'done': True})}\n\n"

    except Exception as e:
        logger.error(f"流式错误: {e}", exc_info=True)
        yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    track_event("chat_end", user.username, req.session_id, {"has_answer": bool(full_answer)})

    await memory.add_message(req.session_id, user.username, "user", req.message)
    if full_answer:
        await memory.add_message(req.session_id, user.username, "assistant", full_answer)

    # 异步触发记忆钩子 (不阻塞响应)
    try:
        history = memory.get_history(req.session_id, user.username)
        if history and len(history) >= 4:
            _asyncio.create_task(H.memory_hooks(req.session_id, user.username, history))
    except Exception:
        pass


async def _handle_rag_fast_channel(req, user, memory):
    """知识库快速通道：将真实 RAG token 直接转为聊天 SSE。"""
    from app.rag.retriever import rag_qa_stream

    history = memory.get_history(req.session_id, user.username)
    rag_query = req.message
    if history:
        context = "\n".join(f"{item.role}: {item.content}" for item in history[-6:])
        rag_query = f"对话历史：\n{context}\n\n用户最新问题：{req.message}"

    answer_parts: list[str] = []
    sources: list[dict] = []
    try:
        async for event in rag_qa_stream(rag_query):
            event_type = event.get("type")
            if event_type == "retrieval":
                sources = event["sources"]
                yield f"data: {json.dumps({'status': '知识库检索完成，正在生成回答...'}, ensure_ascii=False)}\n\n"
            elif event_type == "content":
                content = event["content"]
                answer_parts.append(content)
                yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"
            elif event_type == "done":
                sources = event["sources"]

        answer = "".join(answer_parts)
        yield f"data: {json.dumps({'type': 'knowledge_result', 'sources': sources}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        await memory.add_message(req.session_id, user.username, "user", req.message)
        if answer:
            await memory.add_message(req.session_id, user.username, "assistant", answer)
        from app.api.analytics import track_event
        track_event("chat_end", user.username, req.session_id, {"has_answer": bool(answer), "route": "rag_fast"})
    except Exception as exc:
        logger.warning("RAG 快速通道失败，降级 Agent: %s", exc)
