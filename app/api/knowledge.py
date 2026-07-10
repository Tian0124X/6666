"""知识库 API — /api/knowledge/* — 接入完整 RAG 链路"""

import os
import json
import asyncio
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from app.models.request import KnowledgeQARequest
from app.models.response import KnowledgeQAResponse, UploadResponse
from app.rag.loader import UniversalDocumentLoader
from app.rag.splitter import split_documents
from app.rag.store import add_documents, delete_by_source, get_unique_sources
from app.rag.retriever import rag_qa
from app.rag.advanced import smart_rag_qa
from app.config import settings
from app.rag.errors import KnowledgeStoreUnavailable

logger = logging.getLogger(__name__)
router = APIRouter()

# ====== 后台索引状态跟踪 ======

_index_status: dict[str, dict] = {}  # filename -> {"status": "pending"|"indexing"|"done"|"error", "chunks": int, "error": str}


async def _background_index(file_path: str, filename: str, pdf_engine: str = "auto"):
    """后台异步索引任务：解析 → 分块 → 向量化"""
    _index_status[filename] = {"status": "indexing", "chunks": 0, "error": ""}
    try:
        docs = await asyncio.to_thread(UniversalDocumentLoader.load, file_path, pdf_engine=pdf_engine)
        if not docs:
            from app.rag.mineru_loader import _mineru_available
            import os
            actual_engine = "mineru" if (_mineru_available and pdf_engine in ("auto", "mineru")) else "pypdf2"
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
            _index_status[filename] = {
                "status": "error", "chunks": 0,
                "error": (
                    f"文档解析后无内容 "
                    f"(引擎: {actual_engine}, 文件大小: {file_size} bytes). "
                    f"{'MinerU 已安装但解析失败，可能是扫描件PDF' if _mineru_available else '建议安装 MinerU: pip install magic-pdf'}"
                ),
            }
            return

        chunks = await asyncio.to_thread(split_documents, docs)
        if not chunks:
            _index_status[filename] = {"status": "error", "chunks": 0, "error": "文档分块后无内容"}
            return

        # 同名文件覆盖时必须先移除旧切片，否则检索会返回过期内容。
        await asyncio.to_thread(delete_by_source, file_path)
        count = await asyncio.to_thread(add_documents, chunks)
        from app.rag.retriever import _invalidate_bm25_cache, warmup_bm25
        _invalidate_bm25_cache()

        # 标记索引完成（图谱改为独立后台任务，不阻塞状态更新）
        _index_status[filename] = {"status": "done", "chunks": count, "error": ""}

        # 后台预热 BM25（避免下次查询冷启动）
        asyncio.create_task(asyncio.to_thread(warmup_bm25, 20))

        # 后台构建图谱 — 独立后台任务，失败不影响索引状态
        from app.rag.indexer import _try_build_graph
        asyncio.create_task(asyncio.to_thread(_try_build_graph, chunks, filename))

        logger.info(f"后台索引完成: {filename} → {count} chunks")
    except Exception as e:
        _index_status[filename] = {"status": "error", "chunks": 0, "error": str(e)}
        logger.error(f"后台索引失败: {filename}: {e}")


@router.post("/qa", response_model=KnowledgeQAResponse, tags=["知识库"])
async def knowledge_qa(req: KnowledgeQARequest):
    """
    知识问答 — 2026 优化链路：
    多查询扩展 → 混合检索(BM25+向量+RRF) → LLM 重排序 → 反幻觉生成 → 来源追溯
    """
    try:
        result = await rag_qa(
            question=req.question,
            k=req.top_k,
            use_expansion=True,
            use_rerank=True,
        )
        return KnowledgeQAResponse(
            answer=result["answer"],
            sources=result["sources"],
            timings_ms=result.get("timings_ms", {}),
        )
    except Exception as e:
        if isinstance(e, KnowledgeStoreUnavailable):
            raise HTTPException(status_code=503, detail="知识库向量服务暂不可用，请检查 pgvector 或 ChromaDB。")
        msg = str(e).lower()
        # ChromaDB / HTTP 连接类错误 → 503
        conn_keywords = ("connect", "closed", "refused", "cannot send", "timeout",
                         "unreachable", "not available", "failed to connect")
        if any(kw in msg for kw in conn_keywords):
            raise HTTPException(
                status_code=503,
                detail=f"知识库服务暂不可用（ChromaDB 未启动？）: {msg}",
            )
        raise HTTPException(status_code=500, detail=f"知识问答失败: {msg}")


@router.post("/qa/simple", response_model=KnowledgeQAResponse, tags=["知识库"])
async def knowledge_qa_simple(req: KnowledgeQARequest):
    """
    简化版知识问答 — 跳过查询扩展和重排序，速度更快。
    适合简单事实性查询。
    """
    try:
        result = await rag_qa(
            question=req.question,
            k=req.top_k,
            use_expansion=False,
            use_rerank=False,
        )
        return KnowledgeQAResponse(
            answer=result["answer"],
            sources=result["sources"],
            timings_ms=result.get("timings_ms", {}),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"知识问答失败: {str(e)}")


@router.get("/index/status", tags=["知识库"])
async def index_status():
    """索引进度概览"""
    from app.rag.indexer import get_index_status
    return get_index_status()


@router.post("/index/rebuild", tags=["知识库"])
async def rebuild_index(directory: str = "data/documents", pdf_engine: str = "auto"):
    """全量重建索引（清空后重新索引整个目录，含路径安全校验）"""
    # 路径沙箱检查
    import os
    allowed_dirs = {"data/documents", "data/uploads", "data/reports"}
    abs_dir = os.path.abspath(directory)
    safe = False
    for allowed in allowed_dirs:
        if abs_dir.startswith(os.path.abspath(allowed) + os.sep) or abs_dir == os.path.abspath(allowed):
            safe = True
            break
    if not safe:
        raise HTTPException(status_code=403, detail=f"不允许的目录: {directory}")

    from app.rag.indexer import reindex_all
    result = reindex_all(directory, pdf_engine=pdf_engine)
    return {
        "status": "ok",
        "total": result.total,
        "indexed": result.indexed,
        "skipped": result.skipped,
        "failed": result.failed,
        "total_chunks": result.total_chunks,
        "elapsed_ms": result.elapsed_ms,
    }


@router.post("/upload", response_model=UploadResponse, tags=["知识库"])
async def upload_document(file: UploadFile = File(...), pdf_engine: str = "auto"):
    """
    上传文档 — 快速保存 + 后台异步索引。
    
    优化流程:
    1. 同步保存文件到磁盘 (<1s)
    2. 触发后台异步索引 (不阻塞响应)
    3. 通过 /api/knowledge/index/status 查询索引进度
    """
    # 安全检查
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    safe_filename = os.path.basename(file.filename)
    if safe_filename != file.filename or ".." in safe_filename:
        raise HTTPException(status_code=400, detail=f"文件名包含非法字符: {file.filename}")

    allowed_exts = {".pdf", ".docx", ".xlsx", ".xls", ".txt", ".csv"}
    ext = os.path.splitext(safe_filename)[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {ext}。支持: {allowed_exts}",
        )

    # 快速保存文件到磁盘
    MAX_SIZE = 50 * 1024 * 1024
    upload_dir = os.path.abspath("data/documents")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, safe_filename)

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=413, detail=f"文件过大: {len(content)} 字节 (上限 {MAX_SIZE} 字节)")
    with open(file_path, "wb") as f:
        f.write(content)

    # 触发后台异步索引
    _index_status[safe_filename] = {"status": "pending", "chunks": 0, "error": ""}
    asyncio.create_task(_background_index(file_path, safe_filename, pdf_engine=pdf_engine))

    logger.info(f"文件已保存，后台索引启动: {safe_filename} ({len(content)} bytes)")
    return UploadResponse(
        status="ok",
        filename=safe_filename,
        chunks=0,
        message=f"✅ 文件已上传，正在后台索引中...",
    )


@router.get("/upload/status/{filename}", tags=["知识库"])
async def get_upload_index_status(filename: str):
    """查询文件的后台索引进度"""
    status = _index_status.get(filename)
    if not status:
        return {"filename": filename, "status": "unknown", "chunks": 0}
    return {"filename": filename, **status}


@router.post("/qa/smart", response_model=KnowledgeQAResponse, tags=["知识库"])
async def knowledge_qa_smart(req: KnowledgeQARequest):
    """
    2026 自适应智能问答：
    Level 0 (直接回答) → Level 1 (标准RAG+缓存) → Level 2 (Agentic RAG/GraphRAG)

    自动判断问题复杂度，选择最优策略，并缓存高频查询结果。
    """
    try:
        result = await smart_rag_qa(req.question)
        return KnowledgeQAResponse(
            answer=result["answer"],
            sources=result.get("sources", []),
            mode=result.get("mode", "standard"),
            level=result.get("level", -1),
            from_cache=result.get("from_cache", False),
            iterations=result.get("iterations", 1),
            timings_ms=result.get("timings_ms", {}),
        )
    except Exception as e:
        if isinstance(e, KnowledgeStoreUnavailable):
            raise HTTPException(status_code=503, detail="知识库向量服务暂不可用，请检查 pgvector 或 ChromaDB。")
        import traceback
        logger.error(f"智能问答失败: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"智能问答失败: {str(e)}")


@router.post("/qa/stream/legacy", tags=["知识库"])
async def knowledge_qa_smart_stream_legacy(req: KnowledgeQARequest, request: Request):
    """
    2026 流式智能问答 — SSE 实时推送检索进度 + 回答内容。

    复用 smart_rag_qa() 引擎，按段落流式输出，用户即时看到回答。
    与 /qa/smart 功能等价，但感知延迟从 15-30s 降到 <2s。
    """
    async def event_generator():
        try:
            # 1. 立即推送状态（用户看到即时反馈）
            yield _sse({"status": "正在分析问题..."})

            # 2. 检查客户端是否已断开
            if await request.is_disconnected():
                return

            # 3. 执行智能 RAG
            from app.rag.advanced import smart_rag_qa
            result = await smart_rag_qa(req.question)

            if await request.is_disconnected():
                return

            # 4. 推送检索结果状态
            mode = result.get("mode", "standard")
            level = result.get("level", -1)
            mode_labels = {"direct": "直接回答", "standard": "标准RAG", "agentic": "Agentic RAG", "graphrag": "GraphRAG"}
            yield _sse({"status": f"📚 检索完成 (模式: {mode_labels.get(mode, mode)})"})

            # 5. 按段落流式推送回答
            answer = result.get("answer", "")
            paragraphs = answer.split("\n")
            for para in paragraphs:
                if await request.is_disconnected():
                    return
                if para.strip():
                    yield _sse({"content": para + "\n"})

            # 6. 推送结构化元数据
            yield _sse({
                "type": "knowledge_result",
                "sources": result.get("sources", []),
                "mode": mode,
                "level": level,
                "from_cache": result.get("from_cache", False),
                "iterations": result.get("iterations", 1),
            })

            # 7. 完成
            yield _sse({"done": True})

        except Exception as e:
            import traceback
            logger.error(f"流式问答失败: {e}\n{traceback.format_exc()}")
            yield _sse({"error": f"问答失败: {str(e)}"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


def _sse(data: dict) -> str:
    """将 dict 序列化为 SSE data 行"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/qa/stream", tags=["知识库"])
async def knowledge_qa_stream(req: KnowledgeQARequest, request: Request):
    """速度优先的真实流式问答：检索完成后立刻输出 LLM token。"""
    async def event_generator():
        try:
            from app.rag.retriever import rag_qa_stream

            yield _sse({"status": "正在检索知识库..."})
            async for event in rag_qa_stream(req.question, k=req.top_k):
                if await request.is_disconnected():
                    return
                event_type = event.get("type")
                if event_type == "retrieval":
                    yield _sse({
                        "status": "检索完成，正在生成回答...",
                        "sources": event["sources"],
                        "timings_ms": event["timings_ms"],
                    })
                elif event_type == "content":
                    yield _sse({"content": event["content"]})
                elif event_type == "done":
                    yield _sse({
                        "type": "knowledge_result",
                        "sources": event["sources"],
                        "timings_ms": event["timings_ms"],
                    })
                    yield _sse({"done": True})
        except KnowledgeStoreUnavailable:
            yield _sse({"error": "知识库向量服务暂不可用，请检查 pgvector 或 ChromaDB。"})
        except Exception as exc:
            logger.exception("知识库流式问答失败")
            yield _sse({"error": f"知识库问答失败: {exc}"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/cache/stats", tags=["知识库"])
async def cache_stats():
    """查询缓存统计"""
    from app.rag.cache import query_cache
    return query_cache.stats


@router.delete("/cache", tags=["知识库"])
async def clear_cache():
    """清空查询缓存"""
    from app.rag.cache import query_cache
    query_cache.clear()
    return {"status": "ok", "message": "缓存已清空"}


@router.delete("/documents/{filename:path}", tags=["知识库"])
async def delete_document(filename: str):
    """从知识库删除文档（含路径遍历防护）"""
    # 安全校验：规范化路径 + 禁止目录穿越
    import os
    docs_dir = os.path.abspath("data/documents")
    raw_path = os.path.normpath(os.path.join(docs_dir, filename))
    real_path = os.path.realpath(raw_path)

    # 确保解析后的路径在允许的目录内
    if not real_path.startswith(docs_dir + os.sep) and real_path != docs_dir:
        raise HTTPException(status_code=403, detail=f"不允许的路径: {filename}")

    if not os.path.exists(real_path):
        raise HTTPException(status_code=404, detail=f"文件不存在: {filename}")

    # 删除向量数据
    count = delete_by_source(real_path)

    # 删除文件
    os.remove(real_path)
    # 清除 BM25 缓存
    from app.rag.retriever import _invalidate_bm25_cache
    _invalidate_bm25_cache()

    return {"status": "ok", "deleted_chunks": count, "filename": filename}


@router.get("/documents", tags=["知识库"])
async def list_documents():
    """列出知识库中的文档"""
    sources = get_unique_sources()
    docs_dir = "data/documents"
    physical_files = set(
        f for f in os.listdir(docs_dir)
        if os.path.isfile(os.path.join(docs_dir, f))
    ) if os.path.exists(docs_dir) else set()

    return {
        "total": len(sources),
        "indexed_documents": sources,
        "uploaded_files": list(physical_files),
    }


@router.get("/diagnostics", tags=["知识库"])
async def rag_diagnostics():
    """RAG 系统诊断信息 — 快速定位 BM25/后端问题"""
    from app.rag.store import _detect_backend, get_document_count
    from app.rag.retriever import _bm25_cache, _get_reranker

    backend = _detect_backend()
    doc_count = get_document_count()

    bm25_status = "empty"
    bm25_doc_count = 0
    if _bm25_cache:
        for key, (retriever, count, _) in _bm25_cache.items():
            bm25_status = "ready"
            bm25_doc_count = count
            break

    # 图谱后端状态
    graph_stats = None
    neo4j_available = False
    lightrag_available = False
    try:
        from app.rag.neo4j_store import get_neo4j_store
        ns = get_neo4j_store()
        neo4j_available = ns is not None and ns.is_available()
    except Exception:
        pass
    try:
        from app.rag.lightrag_store import get_lightrag_store
        ls = get_lightrag_store()
        if ls:
            lightrag_available = ls.is_available()
            graph_stats = ls.get_stats()
    except Exception:
        pass

    return {
        "vector_backend": backend,
        "document_count": doc_count,
        "embedding_model": settings.RAG_EMBEDDING_MODEL,
        "embedding_dimension": settings.RAG_EMBEDDING_DIMENSION,
        "bm25_status": bm25_status,
        "bm25_document_count": bm25_doc_count,
        "reranker_available": _get_reranker() is not None,
        "llm_available": settings.is_llm_available,
        "chromadb_url": f"http://{settings.CHROMA_HOST}:{settings.CHROMA_PORT}",
        "pgvector_available": backend == "pgvector",
        "graph_backend": settings.GRAPH_BACKEND,
        "lightrag_available": lightrag_available,
        "neo4j_available": neo4j_available,
        "graph_stats": graph_stats,
    }
