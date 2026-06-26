"""知识库 API — /api/knowledge/* — 接入完整 RAG 链路"""

import os
import asyncio
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.models.request import KnowledgeQARequest
from app.models.response import KnowledgeQAResponse, UploadResponse
from app.rag.loader import UniversalDocumentLoader
from app.rag.splitter import split_documents
from app.rag.store import add_documents, delete_by_source, get_unique_sources
from app.rag.retriever import rag_qa
from app.rag.advanced import smart_rag_qa

logger = logging.getLogger(__name__)
router = APIRouter()

# ====== 后台索引状态跟踪 ======

_index_status: dict[str, dict] = {}  # filename -> {"status": "pending"|"indexing"|"done"|"error", "chunks": int, "error": str}


async def _background_index(file_path: str, filename: str):
    """后台异步索引任务：解析 → 分块 → 向量化"""
    _index_status[filename] = {"status": "indexing", "chunks": 0, "error": ""}
    try:
        docs = await asyncio.to_thread(UniversalDocumentLoader.load, file_path)
        if not docs:
            _index_status[filename] = {"status": "error", "chunks": 0, "error": "文档解析后无内容"}
            return

        chunks = await asyncio.to_thread(split_documents, docs)
        if not chunks:
            _index_status[filename] = {"status": "error", "chunks": 0, "error": "文档分块后无内容"}
            return

        count = await asyncio.to_thread(add_documents, chunks)
        from app.rag.retriever import _invalidate_bm25_cache
        _invalidate_bm25_cache()

        _index_status[filename] = {"status": "done", "chunks": count, "error": ""}
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
        )
    except Exception as e:
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
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"知识问答失败: {str(e)}")


@router.get("/index/status", tags=["知识库"])
async def index_status():
    """索引进度概览"""
    from app.rag.indexer import get_index_status
    return get_index_status()


@router.post("/index/rebuild", tags=["知识库"])
async def rebuild_index(directory: str = "data/documents"):
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
    result = reindex_all(directory)
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
async def upload_document(file: UploadFile = File(...)):
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
    asyncio.create_task(_background_index(file_path, safe_filename))

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
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"智能问答失败: {str(e)}")


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
