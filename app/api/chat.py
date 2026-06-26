"""对话 API — 接入 LangGraph Agent 引擎 + 会话历史管理 + 多用户隔离

2026 优化: 长对话自动摘要压缩, O(1) 上下文窗口; 所有端点强制 require_user
"""

import json
import os
import logging
from typing import List
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse, FileResponse
from app.config import settings
from app.models.request import ChatRequest
from app.models.response import ChatResponse
from app.agent.graph import run_agent
from app.agent.router import classify_task
from app.memory.store import get_memory_store
from app.tools.image_analyzer import save_uploaded_image, analyze_image, is_image_file
from app.models.user import UserInfo
from app.api.auth import require_user

logger = logging.getLogger(__name__)
router = APIRouter()

# 对话历史压缩阈值
MAX_HISTORY_MESSAGES = 6
COMPRESS_AFTER = 8      # 超过 8 条消息触发压缩


def _compress_history(history: list) -> str:
    """
    对话历史智能压缩: 将旧消息总结为一句话摘要。

    优化前: 取最近 6 条原始消息 → 可能 3000+ tokens
    优化后: 旧消息压缩为 1 条摘要 + 最近 4 条原始消息 → ~800 tokens

    Token 节省: ~60-70% (长对话场景)
    """
    # 取最近消息
    recent = history[-MAX_HISTORY_MESSAGES:]
    older = history[:-MAX_HISTORY_MESSAGES] if len(history) > MAX_HISTORY_MESSAGES else []

    if not older:
        # 短对话: 直接拼接
        return "\n".join(
            f"[{m.role}]: {m.content[:300]}" for m in history
        )

    # 长对话: 压缩旧消息
    summary_parts = []
    for m in older[-4:]:  # 只摘要最近 4 条旧消息
        summary_parts.append(f"{m.role}: {m.content[:80]}")
    summary = " | ".join(summary_parts)

    # 用 LLM 生成简洁摘要 (可选, 太耗时则跳过)
    if settings.is_llm_available and len(older) > 4:
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import SystemMessage, HumanMessage
            llm = ChatOpenAI(
                model=settings.LLM_MODEL,
                api_key=settings.LLM_API_KEY,
                base_url=settings.LLM_BASE_URL,
                temperature=0, timeout=10,
            )
            response = llm.invoke([
                SystemMessage(content="将以下对话历史总结为一句话摘要。只输出摘要。"),
                HumanMessage(content="\n".join(
                    f"{m.role}: {m.content[:200]}" for m in older[-6:]
                )),
            ])
            summary = f"[历史摘要] {response.content.strip()}"
        except Exception:
            summary = f"[历史摘要] {summary}"  # 规则降级

    # 拼接: 摘要 + 最近消息
    recent_str = "\n".join(
        f"[{m.role}]: {m.content[:300]}" for m in recent
    )
    return f"{summary}\n\n{recent_str}"


@router.post("/chat", response_model=ChatResponse, tags=["对话"])
async def chat(req: ChatRequest, user: UserInfo = Depends(require_user)):
    """
    对话接口 — 自动路由简单/复杂任务，调用 LangGraph Agent 引擎。
    需要登录。user_id 从 Bearer token 推导，忽略请求体中的 user_id。
    """
    try:
        memory = await get_memory_store()
        history = memory.get_history(req.session_id, user.username)

        # 构建带上下文的输入 (长对话自动压缩)
        if history:
            context = _compress_history(history)
            full_input = f"对话历史：\n{context}\n\n用户最新问题：{req.message}"
        else:
            full_input = req.message

        # 分类
        task_type = classify_task(full_input) or "simple"

        # 执行: complex 任务使用多Agent协作
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

        # 存储对话
        await memory.add_message(req.session_id, user.username, "user", req.message)
        await memory.add_message(req.session_id, user.username, "assistant", answer)

        return ChatResponse(answer=answer, task_type=task_type)
    except Exception as e:
        logger.error(f"对话处理失败: {e}", exc_info=True)
        return ChatResponse(
            answer=f"处理过程中出现错误: {str(e)}",
            task_type="simple",
        )


@router.post("/chat/stream", tags=["对话"])
async def chat_stream(req: ChatRequest, user: UserInfo = Depends(require_user)):
    """
    流式对话 — SSE 实时推送，通过 LangGraph Agent 引擎。
    使用 LangGraph astream_events() 获取 token 级流式输出。
    需要登录。user_id 从 Bearer token 推导。
    """
    from app.agent.graph import get_agent_app
    from app.agent.state import AgentState
    from langchain_core.messages import HumanMessage

    async def event_generator():
        memory = await get_memory_store()

        async def _stream_data_result(result: dict, route_label: str):
            """统一的 SSE 数据结果输出 — 复用于快速通道和兜底路径"""
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
            if has_result or has_chart or code or has_insights:
                data_event = {"type": "data_result"}
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
                yield f"data: {json.dumps(data_event, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"

            await memory.add_message(req.session_id, user.username, "user", req.message)
            await memory.add_message(req.session_id, user.username, "assistant", answer_text)

            from app.api.analytics import track_event
            track_event("chat_end", user.username, req.session_id, {"has_answer": True, "route": route_label})

        # ====== 统一意图路由 ======
        from app.agent.intent import (
            classify_intent, Intent, IntentResult,
            extract_file_path, has_data_question,
        )

        file_path = extract_file_path(req.message)
        has_file = bool(file_path)
        intent = classify_intent(req.message, has_file=has_file)

        logger.info(
            f"意图路由: {intent.primary.value} conf={intent.confidence} "
            f"has_file={has_file} user={user.username} | {req.message[:60]}..."
        )

        # --- 数据对话通道: data_analysis / data_report ---
        if intent.primary in (Intent.DATA_ANALYSIS, Intent.DATA_REPORT):
            import asyncio
            from app.tools.data_conversation import analyze_with_llm

            # 确定文件路径
            if file_path:
                target_file = file_path
                user_question = intent.reason  # 从消息中提取的问题部分
                # 重新提取清理后的问题
                import re as _re
                user_question = _re.sub(
                    r'\[已上传数据文件:\s*[^\]]+\]\s*', '', req.message
                ).replace('用户问题:', '').strip()
                route_label = "data_fast"
            else:
                # 无文件但有数据意图 → 使用示例数据
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
                result = await asyncio.to_thread(
                    analyze_with_llm, target_file, user_question, req.with_chart
                )
            except Exception as e:
                logger.error(f"数据分析失败: {e}", exc_info=True)
                yield f"data: {json.dumps({'content': f'数据分析失败: {e}'}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
                return

            async for chunk in _stream_data_result(result, route_label):
                yield chunk

            # 如果是 data_report 意图且有文件，额外提示可下载报告
            if intent.primary == Intent.DATA_REPORT and file_path:
                yield f"data: {json.dumps({'content': '\n\n---\n📥 需要下载 Word 报告？点击下方按钮或回复「生成报告」。'}, ensure_ascii=False)}\n\n"

            return

        # --- greeting → 标准 Agent 通道（自然闲聊）---
        # --- knowledge_qa / oa_query / crm_query → Agent 通道 ---
        # --- general_chat / multi_domain → Agent 通道 ---
        # (所有非数据意图统一走 Agent，Agent 内部按工具描述自动选择)

        # ====== 标准通道: Agent 对话 ======
        history = memory.get_history(req.session_id, user.username)

        # 注入用户画像 (语义记忆)
        from app.memory.semantic import inject_facts_to_prompt
        user_profile = inject_facts_to_prompt(user.username)
        from langchain_core.messages import SystemMessage as LCMessage

        # 构建对话历史消息 (长对话自动压缩)
        msgs: list = []
        if history and len(history) > COMPRESS_AFTER:
            # 长对话: 注入摘要作为 system 消息
            compressed = _compress_history(history)
            system_text = f"对话历史摘要: {compressed}"
            if user_profile:
                system_text = user_profile + "\n\n" + system_text
            msgs.append(LCMessage(content=system_text))
            # 只带最近 4 条原始消息
            for m in history[-4:]:
                if m.role == "user":
                    msgs.append(HumanMessage(content=m.content))
                elif m.role == "assistant":
                    from langchain_core.messages import AIMessage
                    msgs.append(AIMessage(content=m.content))
        elif history:
            if user_profile:
                msgs.append(LCMessage(content=user_profile))
            for m in history[-MAX_HISTORY_MESSAGES:]:
                if m.role == "user":
                    msgs.append(HumanMessage(content=m.content))
                elif m.role == "assistant":
                    from langchain_core.messages import AIMessage
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

            # 使用 astream_events 获取实时事件流
            total_tokens = 0
            async for event in app.astream_events(initial, config, version="v2"):
                kind = event.get("event", "")
                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        full_answer += chunk.content
                        yield f"data: {json.dumps({'content': chunk.content}, ensure_ascii=False)}\n\n"
                    # 提取 token 用量 (LangGraph/LangChain usage_metadata)
                    if chunk and hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                        total_tokens = chunk.usage_metadata.get("total_tokens", total_tokens)

                elif kind == "on_custom_event":
                    name = event.get("name", "")
                    if name == "tool_start":
                        tool_name = event.get("data", {}).get("name", "")
                        from app.api.monitoring import track_tool_call
                        track_tool_call(tool_name)
                        yield f"data: {json.dumps({'status': f'🔧 调用工具: {tool_name}...'}, ensure_ascii=False)}\n\n"

            # 记录 token 消耗
            if total_tokens > 0:
                from app.api.monitoring import track_token_usage
                track_token_usage(total_tokens)

            # 如果 astream_events 没有产生流式输出（降级），回退到直接调用
            if not full_answer:
                result = await app.ainvoke(initial, config)
                full_answer = result.get("final_answer", "抱歉，处理失败。")
                yield f"data: {json.dumps({'content': full_answer}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            logger.error(f"流式错误: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

        from app.api.analytics import track_event
        track_event("chat_end", user.username, req.session_id, {"has_answer": bool(full_answer)})

        await memory.add_message(req.session_id, user.username, "user", req.message)
        if full_answer:
            await memory.add_message(req.session_id, user.username, "assistant", full_answer)

        # 异步触发记忆钩子 (摘要 + 事实提取, 不阻塞响应)
        try:
            history = memory.get_history(req.session_id, user.username)
            if history and len(history) >= 4:
                import asyncio as _asyncio
                _asyncio.create_task(_memory_hooks(req.session_id, user.username, history))
        except Exception:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ====== 会话管理 API ======


@router.post("/sessions", tags=["会话"])
async def create_session(
    user: UserInfo = Depends(require_user),
    name: str = Query(default="新对话", description="会话名称"),
):
    """创建新会话。返回 session_id。"""
    from app.memory.session import create_session as create_sess
    session = create_sess(user.username, name)
    return {"session": session}


@router.get("/sessions", tags=["会话"])
async def list_sessions(user: UserInfo = Depends(require_user)):
    """列出当前用户的所有会话（按更新时间倒序）"""
    from app.memory.session import list_sessions as list_sess
    sessions = list_sess(user.username)
    return {"sessions": sessions, "total": len(sessions)}


@router.delete("/sessions/{session_id}", tags=["会话"])
async def delete_session(
    session_id: str,
    user: UserInfo = Depends(require_user),
):
    """删除会话及其所有消息。需为会话所有者。"""
    from app.memory.session import delete_session as delete_sess
    ok = delete_sess(session_id, user.username)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")
    return {"status": "ok", "message": f"会话 {session_id} 已删除"}


@router.patch("/sessions/{session_id}", tags=["会话"])
async def rename_session(
    session_id: str,
    user: UserInfo = Depends(require_user),
    name: str = Query(..., description="新名称"),
):
    """重命名会话。需为会话所有者。"""
    from app.memory.session import rename_session as rename_sess
    ok = rename_sess(session_id, user.username, name)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")
    return {"status": "ok", "session_id": session_id, "name": name}


@router.patch("/sessions/{session_id}/archive", tags=["会话"])
async def toggle_archive_session(
    session_id: str,
    user: UserInfo = Depends(require_user),
    archived: bool = Query(default=True, description="true=归档, false=取消归档"),
):
    """归档/取消归档会话。需为会话所有者。"""
    from app.memory.session import archive_session
    ok = archive_session(session_id, user.username, archived)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")
    return {"status": "ok", "session_id": session_id, "is_archived": archived}


# ====== 会话历史管理 ======


@router.get("/chat/history", tags=["对话"])
async def list_conversations(user: UserInfo = Depends(require_user)):
    """列出当前用户的所有会话历史 (从 MySQL + Redis，自动按 user 隔离)"""
    from app.models.database import get_session as get_db, ConversationRecord
    from sqlalchemy import func, desc

    sessions = []
    db = get_db()
    if db:
        try:
            # MySQL: 按 session_id 分组，只查当前用户的
            rows = (
                db.query(
                    ConversationRecord.session_id,
                    ConversationRecord.user_id,
                    func.min(ConversationRecord.created_at).label("started"),
                    func.max(ConversationRecord.created_at).label("updated"),
                    func.count().label("messages"),
                    func.substr(func.group_concat(ConversationRecord.content), 1, 100).label("preview"),
                )
                .filter(ConversationRecord.user_id == user.username)
                .group_by(ConversationRecord.session_id, ConversationRecord.user_id)
                .order_by(desc("updated"))
                .limit(50)
                .all()
            )
            for r in rows:
                sessions.append({
                    "session_id": r.session_id,
                    "user_id": r.user_id,
                    "started_at": r.started.isoformat() if r.started else "",
                    "updated_at": r.updated.isoformat() if r.updated else "",
                    "message_count": r.messages,
                    "preview": (r.preview or "")[:100],
                })
        except Exception as e:
            logger.warning(f"MySQL 查询历史失败: {e}")
        finally:
            db.close()

    # 补充 Redis 中的数据 (仅当前用户)
    seen = {s["session_id"] for s in sessions}
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, decode_responses=True)
        for key in r.scan_iter(f"chat:{user.username}:*"):
            parts = key.replace("chat:", "").split(":", 1)
            if len(parts) == 2:
                uid, sid = parts
                if sid not in seen:
                    msgs_raw = r.lrange(key, 0, 0)
                    preview = ""
                    if msgs_raw:
                        try:
                            preview = json.loads(msgs_raw[0]).get("content", "")[:100]
                        except Exception:
                            pass
                    sessions.append({
                        "session_id": sid,
                        "user_id": uid,
                        "started_at": "",
                        "updated_at": "",
                        "message_count": r.llen(key),
                        "preview": preview,
                    })
    except Exception:
        pass

    return {"sessions": sessions, "total": len(sessions)}


@router.get("/chat/history/{session_id}", tags=["对话"])
async def get_conversation(session_id: str, user: UserInfo = Depends(require_user)):
    """获取指定会话的完整消息历史。需为会话所有者。"""
    from app.models.database import get_session as get_db, ConversationRecord

    messages = []
    db = get_db()
    if db:
        try:
            from sqlalchemy import asc
            rows = (
                db.query(ConversationRecord)
                .filter(
                    ConversationRecord.session_id == session_id,
                    ConversationRecord.user_id == user.username,
                )
                .order_by(asc(ConversationRecord.created_at))
                .all()
            )
            for r in rows:
                messages.append({
                    "role": r.role,
                    "content": r.content,
                    "time": r.created_at.isoformat() if r.created_at else "",
                })
        except Exception as e:
            logger.warning(f"MySQL 查询消息失败: {e}")
        finally:
            db.close()

    # 补充 Redis/内存
    memory = await get_memory_store()
    local = memory.get_history(session_id, user.username)
    if not messages and local:
        messages = [{"role": m.role, "content": m.content, "time": m.timestamp.isoformat()} for m in local]

    # 如果 MySQL 和 Redis 都没数据，检查是否有其他用户的 session → 403
    if not messages:
        from app.memory.session import get_session_owner
        owner = get_session_owner(session_id)
        if owner and owner != user.username:
            raise HTTPException(status_code=403, detail="无权访问该会话")

    return {"session_id": session_id, "messages": messages, "total": len(messages)}


@router.delete("/chat/history/{session_id}", tags=["对话"])
async def delete_conversation(session_id: str, user: UserInfo = Depends(require_user)):
    """删除指定会话。需为会话所有者。"""
    from app.models.database import get_session as get_db, ConversationRecord

    # MySQL (加 user_id 过滤)
    deleted = False
    db = get_db()
    if db:
        try:
            result = db.query(ConversationRecord).filter(
                ConversationRecord.session_id == session_id,
                ConversationRecord.user_id == user.username,
            ).delete()
            db.commit()
            deleted = result > 0
        except Exception as e:
            logger.warning(f"MySQL 删除失败: {e}")
        finally:
            db.close()

    # Redis + 内存
    memory = await get_memory_store()
    await memory.clear(session_id, user.username)

    if not deleted:
        # 可能只有 Redis 数据
        from app.memory.session import get_session_owner
        owner = get_session_owner(session_id)
        if owner and owner != user.username:
            raise HTTPException(status_code=403, detail="无权删除该会话")
        if not owner:
            raise HTTPException(status_code=404, detail="会话不存在")

    return {"status": "ok", "message": f"会话 {session_id} 已删除"}


# ====== Human-in-the-Loop 审批 ======


@router.get("/chat/approvals", tags=["对话"])
async def list_approvals(user: UserInfo = Depends(require_user)):
    """列出当前用户的所有等待审批的操作"""
    from app.agent.human_loop import list_all_pending
    all_pending = list_all_pending()
    # 过滤出当前用户的审批
    user_pending = [
        p for p in all_pending
        if p.get("thread_id", "").startswith(f"{user.username}:")
    ]
    return {"pending": user_pending}


@router.get("/chat/approvals/{thread_id}", tags=["对话"])
async def check_approval(thread_id: str, user: UserInfo = Depends(require_user)):
    """检查是否有待审批操作"""
    from app.agent.human_loop import get_pending
    pending = get_pending(thread_id)
    if pending:
        return {"pending": True, "approval": pending}
    return {"pending": False}


@router.post("/chat/approvals/{thread_id}/approve", tags=["对话"])
async def approve_action(thread_id: str, user: UserInfo = Depends(require_user)):
    """批准操作"""
    from app.agent.human_loop import approve
    ok = approve(thread_id)
    if not ok:
        raise HTTPException(status_code=404, detail="无待审批操作")
    return {"status": "approved"}


@router.post("/chat/approvals/{thread_id}/reject", tags=["对话"])
async def reject_action(thread_id: str, user: UserInfo = Depends(require_user), reason: str = ""):
    """拒绝操作"""
    from app.agent.human_loop import reject
    ok = reject(thread_id, reason)
    if not ok:
        raise HTTPException(status_code=404, detail="无待审批操作")
    return {"status": "rejected"}


# ====== 多模态: 图片上传 + 分析 ======

from fastapi import UploadFile, File, Form


@router.post("/chat/image", tags=["对话"])
async def analyze_chat_image(
    file: UploadFile = File(...),
    question: str = Form(default="请描述这张图片的内容"),
    user: UserInfo = Depends(require_user),
):
    """
    上传图片进行分析（截图提问、图表分析、OCR文字提取）

    支持: PNG, JPG, GIF, BMP, WebP, TIFF
    """
    if not file.filename or not is_image_file(file.filename):
        supported = ".png, .jpg, .jpeg, .gif, .bmp, .webp, .tiff"
        raise HTTPException(status_code=400, detail=f"不支持的图片格式，支持: {supported}")

    # 大小限制 10MB
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="图片过大 (上限10MB)")

    path = save_uploaded_image(data, file.filename)

    # 分析图片
    analysis_text = analyze_image(path, question)

    # 如果需要LLM分析
    if settings.is_llm_available and question:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage
        try:
            llm = ChatOpenAI(
                model=settings.LLM_MODEL,
                api_key=settings.LLM_API_KEY,
                base_url=settings.LLM_BASE_URL,
                temperature=0.3, timeout=settings.LLM_TIMEOUT,
            )
            response = llm.invoke([
                SystemMessage(content="你是多模态分析助手。根据图片的OCR文字和元数据，回答用户问题。如果是图表请分析趋势，如果是文档请提取关键信息。"),
                HumanMessage(content=analysis_text),
            ])
            answer = response.content
        except Exception as e:
            answer = analysis_text + f"\n\n⚠️ LLM分析失败: {e}"
    else:
        answer = analysis_text

    return {
        "status": "ok",
        "filename": file.filename,
        "image_path": path,
        "analysis": analysis_text,
        "answer": answer,
    }


# ====== 报告下载 ======

@router.get("/chat/report/generate")
async def generate_and_download_report(
    file_path: str = Query(..., description="数据文件路径"),
    session_id: str = Query(default="default"),
    user: UserInfo = Depends(require_user),
):
    """
    生成 Word 数据分析报告并返回下载。
    使用方式: GET /api/chat/report/generate?file_path=data/documents/xxx.xlsx&session_id=xxx
    """
    import asyncio
    from app.tools.data_conversation import generate_data_report
    from app.tools.registry import validate_file_path
    from fastapi.responses import FileResponse

    # 安全校验
    try:
        safe_path = validate_file_path(file_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not os.path.exists(safe_path):
        raise HTTPException(status_code=404, detail=f"文件不存在: {safe_path}")

    # 在后台线程生成报告（同步IO操作）
    try:
        report_path = await asyncio.to_thread(generate_data_report, safe_path)
    except Exception as e:
        logger.error(f"报告生成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"报告生成失败: {e}")

    if not os.path.exists(report_path):
        raise HTTPException(status_code=500, detail="报告生成后文件不存在")

    filename = os.path.basename(report_path)
    return FileResponse(
        report_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ====== 记忆 API (情景 + 语义) ======

from pydantic import BaseModel as PydanticModel


class FactSearchRequest(PydanticModel):
    query: str = ""
    category: str = ""


@router.get("/memory/facts", tags=["记忆"])
async def get_facts(
    user: UserInfo = Depends(require_user),
    category: str = Query(default=""),
):
    """获取当前用户的记忆事实。可按 category 过滤 (preference/fact/context)。"""
    from app.memory.semantic import get_user_facts
    facts = get_user_facts(user.username, category=category or None)
    return {"facts": facts, "total": len(facts)}


@router.post("/memory/facts/search", tags=["记忆"])
async def search_facts(req: FactSearchRequest, user: UserInfo = Depends(require_user)):
    """搜索用户记忆事实（当前为 MySQL LIKE 匹配，后续可扩展到 pgvector 语义搜索）。"""
    from app.memory.semantic import get_user_facts
    all_facts = get_user_facts(user.username, category=req.category or None)
    if req.query:
        q = req.query.lower()
        all_facts = [f for f in all_facts if q in f["fact"].lower()]
    return {"facts": all_facts, "total": len(all_facts)}


@router.get("/memory/summary/{session_id}", tags=["记忆"])
async def get_session_summary(
    session_id: str,
    user: UserInfo = Depends(require_user),
):
    """获取指定会话的结构化摘要。"""
    from app.memory.summarizer import get_summary
    summary = get_summary(session_id, user.username)
    if summary:
        return {"summary": summary}
    return {"summary": None}


# ====== 记忆触发钩子 (内部，非端点) ======

async def _memory_hooks(session_id: str, user_id: str, messages: list, is_session_end: bool = False):
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
