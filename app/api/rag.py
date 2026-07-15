"""知识库 RAG 的唯一 HTTP 接口。"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.rag.errors import KnowledgeStoreUnavailable
from app.rag.loader import UniversalDocumentLoader
from app.rag.quality import build_index_quality_report
from app.rag.retriever import rag_qa, rag_qa_stream
from app.memory.profile import user_preference_memory
from app.memory.session import session_memory
from app.api.auth import get_current_user, require_user
from app.models.user import UserInfo
from app.rag.splitter import split_documents
from app.rag.store import (
    add_documents,
    delete_by_source,
    get_document_count,
    get_document_summaries,
    get_evidence,
    get_unique_sources,
    resolve_document_path,
)

router = APIRouter(tags=["知识库 RAG"])
DOCUMENTS_DIR = Path("data/documents").resolve()
FEEDBACK_FILE = Path("data/rag-feedback.jsonl")
_index_status: dict[str, dict] = {}


class RagTurn(BaseModel):
    """前端保存的最小 RAG 会话上下文。"""

    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class RagAnswerRequest(BaseModel):
    """RAG 问答请求；会话记忆优先由服务端按 session_id 读取。"""

    question: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(default="default", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    history: list[RagTurn] = Field(default_factory=list, max_length=8)
    top_k: int = Field(default=5, ge=1, le=8)


class RagFeedbackRequest(BaseModel):
    """用户对回答和来源的可追溯反馈。"""

    question: str = Field(min_length=1, max_length=4000)
    answer: str = Field(min_length=1, max_length=12000)
    verdict: str = Field(pattern="^(useful|not_useful|wrong_source)$")
    citation_id: str | None = Field(default=None, max_length=20)
    note: str = Field(default="", max_length=1000)
    sources: list[dict] = Field(default_factory=list, max_length=8)


class UserPreferenceRequest(BaseModel):
    """用户主动保存的回答表达偏好。"""

    fact_text: str = Field(min_length=1, max_length=512)
    session_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _index_file(path: Path, filename: str) -> None:
    """后台完成解析、分块和索引，上传接口不等待模型计算。"""
    _index_status[filename] = {"status": "indexing", "stage": "正在解析文档", "chunks": 0, "error": ""}
    try:
        documents = await asyncio.to_thread(UniversalDocumentLoader.load, str(path))
        _index_status[filename].update({"stage": "正在拆分证据"})
        chunks = await asyncio.to_thread(split_documents, documents)
        if not chunks:
            raise ValueError("文档未解析出可索引内容")
        quality = await asyncio.to_thread(build_index_quality_report, path, documents, chunks)
        _index_status[filename].update({"stage": "正在写入知识库", "chunks": len(chunks)})
        replaced_chunks = await asyncio.to_thread(delete_by_source, str(path))
        count = await asyncio.to_thread(add_documents, chunks)
        quality["replaced_chunks"] = replaced_chunks
        _index_status[filename] = {
            "status": "done", "stage": "已可用于问答", "chunks": count, "error": "",
            "quality": quality,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        _index_status[filename] = {"status": "error", "stage": "索引失败", "chunks": 0, "error": str(exc)}


@router.post("/answers")
async def answer(request: RagAnswerRequest):
    """非流式问答接口，便于评测和脚本调用。"""
    try:
        return await rag_qa(request.question, k=request.top_k)
    except KnowledgeStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/answers/stream")
async def answer_stream(
    request: RagAnswerRequest,
    http_request: Request,
    user: UserInfo = Depends(get_current_user),
):
    """先推送证据，再推送回答 token 与最终过程指标。"""
    async def events():
        try:
            yield _sse({"type": "status", "stage": "retrieval", "message": "正在检索知识库…"})
            # 优先使用服务端会话记忆；旧客户端仍可传入 history 作为兼容回退。
            history = await asyncio.to_thread(
                session_memory.get_recent_turns,
                user.username,
                request.session_id,
                settings.RAG_MEMORY_RECENT_TURNS,
            )
            if not history:
                history = [turn.model_dump() for turn in request.history]
            summary_reader = getattr(session_memory, "get_summary", None)
            summary = (
                await asyncio.to_thread(summary_reader, user.username, request.session_id)
                if callable(summary_reader) else ""
            )
            preferences = await asyncio.to_thread(
                user_preference_memory.list_preferences,
                user.username,
                settings.RAG_MEMORY_PREFERENCE_LIMIT,
            )
            memory_notes: list[dict[str, str]] = []
            if summary:
                memory_notes.append({
                    "role": "system",
                    "content": f"这是当前会话的抽取式摘要，仅用于理解追问，不是知识证据：\n{summary}",
                })
            if preferences:
                preference_text = "；".join(item["fact_text"] for item in preferences)
                memory_notes.append({
                    "role": "system",
                    "content": f"这是用户明确的表达偏好，只影响回答形式，不是知识证据：{preference_text}",
                })
            history = memory_notes + history
            await asyncio.to_thread(
                session_memory.append_turn, user.username, request.session_id, "user", request.question
            )
            answer_parts: list[str] = []
            async for event in rag_qa_stream(request.question, request.top_k, history):
                if await http_request.is_disconnected():
                    return
                if event.get("type") == "content":
                    answer_parts.append(str(event.get("content", "")))
                elif event.get("type") == "replace_content":
                    answer_parts = [str(event.get("content", ""))]
                yield _sse(event)
            await asyncio.to_thread(
                session_memory.append_turn, user.username, request.session_id, "assistant", "".join(answer_parts)
            )
            summary_refresher = getattr(session_memory, "refresh_summary", None)
            if callable(summary_refresher):
                await asyncio.to_thread(
                    summary_refresher,
                    user.username,
                    request.session_id,
                    settings.RAG_MEMORY_SUMMARY_TRIGGER_TURNS,
                    settings.RAG_MEMORY_SUMMARY_SOURCE_TURNS,
                )
        except KnowledgeStoreUnavailable as exc:
            yield _sse({"type": "error", "message": str(exc)})
        except Exception as exc:
            yield _sse({"type": "error", "message": f"RAG 问答失败: {exc}"})

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/memory/preferences")
async def list_memory_preferences(user: UserInfo = Depends(require_user)):
    """列出当前登录用户主动保存的表达偏好。"""
    return {"preferences": await asyncio.to_thread(
        user_preference_memory.list_preferences,
        user.username,
        settings.RAG_MEMORY_PREFERENCE_LIMIT,
    )}


@router.post("/memory/preferences")
async def save_memory_preference(
    request: UserPreferenceRequest,
    user: UserInfo = Depends(require_user),
):
    """保存可撤回的用户偏好，不从模型回复自动抽取。"""
    try:
        preference = await asyncio.to_thread(
            user_preference_memory.save_preference,
            user.username,
            request.fact_text,
            request.session_id,
        )
        return {"status": "ok", "preference": preference}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/memory/preferences/{preference_id}")
async def delete_memory_preference(
    preference_id: str,
    user: UserInfo = Depends(require_user),
):
    """按用户归属删除偏好，避免跨用户遗忘。"""
    deleted = await asyncio.to_thread(
        user_preference_memory.delete_preference,
        user.username,
        preference_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="偏好不存在")
    return {"status": "ok"}


@router.get("/memory/sessions/{session_id}/summary")
async def get_memory_summary(
    session_id: str,
    user: UserInfo = Depends(require_user),
):
    """读取当前用户指定会话的摘要，便于用户检查长期记忆。"""
    if not session_id.replace("_", "").replace("-", "").isalnum() or len(session_id) > 64:
        raise HTTPException(status_code=400, detail="会话 ID 不合法")
    return {"session_id": session_id, "summary": await asyncio.to_thread(
        session_memory.get_summary,
        user.username,
        session_id,
    )}


@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """保存原文件并异步建立可追溯索引。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    filename = os.path.basename(file.filename)
    if filename != file.filename or ".." in filename:
        raise HTTPException(status_code=400, detail="文件名不合法")
    if Path(filename).suffix.lower() not in {".pdf", ".docx", ".xlsx", ".xls", ".txt", ".csv"}:
        raise HTTPException(status_code=400, detail="暂不支持该文件类型")
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件不能超过 50MB")
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    target = DOCUMENTS_DIR / filename
    with target.open("wb") as output:
        output.write(content)
    _index_status[filename] = {"status": "pending", "stage": "文件已上传，等待索引", "chunks": 0, "error": ""}
    asyncio.create_task(_index_file(target, filename))
    return {"status": "accepted", "filename": filename, "chunks": 0, "stage": "文件已上传，正在建立索引"}


@router.get("/documents")
async def list_documents():
    """返回已索引文档及上传后的索引状态。"""
    indexed = {item["filename"]: item for item in get_document_summaries()}
    files = {item.name: item for item in DOCUMENTS_DIR.glob("*") if item.is_file()} if DOCUMENTS_DIR.exists() else {}
    names = sorted(set(indexed) | set(files))
    documents = []
    for filename in names:
        task = _index_status.get(filename, {})
        summary = indexed.get(filename, {})
        status = task.get("status") or ("done" if summary else "pending")
        item = {
            "filename": filename,
            "document_id": summary.get("document_id"),
            "chunks": task.get("chunks", summary.get("chunks", 0)),
            "status": status,
            "stage": task.get("stage") or ("已可用于问答" if summary else "等待重新索引"),
            "error": task.get("error", ""),
            "completed_at": task.get("completed_at"),
            "size": files[filename].stat().st_size if filename in files else None,
        }
        if task.get("quality"):
            item["quality"] = task["quality"]
        documents.append(item)
    return {
        "documents": documents,
        "total_chunks": get_document_count(),
    }


@router.get("/documents/{filename}/status")
async def document_status(filename: str):
    """查询单个上传任务状态。"""
    return {"filename": filename, **_index_status.get(filename, {"status": "unknown", "chunks": 0, "error": ""})}


@router.delete("/documents/{filename}")
async def delete_document(filename: str):
    """删除原文件及其全部索引切片。"""
    safe_name = os.path.basename(filename)
    if safe_name != filename:
        raise HTTPException(status_code=400, detail="文件名不合法")
    target = (DOCUMENTS_DIR / safe_name).resolve()
    if DOCUMENTS_DIR not in target.parents:
        raise HTTPException(status_code=400, detail="文件路径不合法")
    delete_by_source(str(target))
    if target.exists():
        target.unlink()
    _index_status.pop(safe_name, None)
    return {"status": "ok"}


@router.get("/citations/{document_id}/{chunk_id}")
async def citation_detail(document_id: str, chunk_id: str):
    """读取单条引用的完整证据和相邻切片。"""
    evidence = get_evidence(document_id, chunk_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="引用不存在或不属于该文档")
    return evidence


@router.get("/documents/{document_id}/download")
async def download_document(document_id: str):
    """仅允许通过稳定文档身份下载知识库原文件。"""
    resolved = resolve_document_path(document_id)
    if resolved is None:
        raise HTTPException(status_code=404, detail="原文件不存在")
    source, filename = resolved
    target = Path(source).resolve()
    if DOCUMENTS_DIR not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="原文件不存在")
    return FileResponse(target, filename=filename)


@router.get("/diagnostics")
async def diagnostics():
    """展示单一 RAG 链路的运行状态，避免隐藏慢路径。"""
    from app.config import settings
    return {
        "backend": "pgvector",
        "document_count": get_document_count(),
        "indexed_documents": get_unique_sources(),
        "embedding_model": settings.RAG_EMBEDDING_MODEL,
        "online_rerank": settings.RAG_ONLINE_RERANK,
        "latency_target": {"retrieval_p95_ms": 1000, "first_token_p95_ms": 2000},
    }


@router.post("/feedback")
async def submit_feedback(feedback: RagFeedbackRequest):
    """将反馈以 JSONL 形式追加保存，供离线评测回放。"""
    record = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        **feedback.model_dump(),
    }
    FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with FEEDBACK_FILE.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"status": "ok", "feedback_id": record["id"]}
