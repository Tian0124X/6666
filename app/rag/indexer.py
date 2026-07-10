"""
文档索引管理 — 批量索引、增量索引、重建索引、索引进度追踪

提供三种索引模式：
  index_file()     — 单文件索引
  index_directory()— 批量目录索引（支持递归、进度回调）
  reindex_all()    — 全量重建索引
"""

import os
import logging
import time
from pathlib import Path
from typing import List, Callable, Optional
from dataclasses import dataclass, field

from app.config import settings
from app.rag.loader import UniversalDocumentLoader
from app.rag.splitter import split_documents
from app.rag.store import add_documents, delete_by_source, get_unique_sources, get_document_count
from app.rag.neo4j_store import get_neo4j_store

logger = logging.getLogger(__name__)


@dataclass
class IndexResult:
    """单文件索引结果"""
    filename: str
    status: str          # "ok" | "skipped" | "failed"
    chunks: int = 0
    elapsed_ms: float = 0
    error: str = ""


@dataclass
class BatchIndexResult:
    """批量索引汇总"""
    total: int = 0
    indexed: int = 0
    skipped: int = 0
    failed: int = 0
    total_chunks: int = 0
    elapsed_ms: float = 0
    files: List[IndexResult] = field(default_factory=list)


def index_file(
    file_path: str,
    force: bool = False,
    pdf_engine: str = "auto",
) -> IndexResult:
    """
    索引单个文件。

    Args:
        file_path: 文件绝对路径
        force: 是否强制重建（跳过已索引检查）
        pdf_engine: PDF 解析引擎 ("auto"/"mineru"/"pypdf2")

    Returns:
        IndexResult
    """
    start = time.time()
    filename = Path(file_path).name

    # 跳过不支持的类型
    ext = Path(file_path).suffix.lower()
    supported = {".pdf", ".docx", ".xlsx", ".xls", ".txt", ".csv"}
    if ext not in supported:
        return IndexResult(
            filename=filename, status="skipped",
            error=f"不支持的文件类型: {ext}",
        )

    # 跳过已索引文件（除非 force=True）
    if not force:
        indexed = get_unique_sources()
        if filename in indexed:
            return IndexResult(
                filename=filename, status="skipped",
                error="已索引（使用 force=True 强制重建）",
            )

    try:
        # 如果已索引，先删旧版本
        abs_path = os.path.abspath(file_path)
        delete_by_source(abs_path)

        # 加载 → 分块 → 入库
        docs = UniversalDocumentLoader.load(file_path, pdf_engine=pdf_engine)
        if not docs:
            # 诊断：尝试获取实际解析引擎信息
            from app.rag.mineru_loader import _mineru_available
            actual_engine = "mineru" if (_mineru_available and pdf_engine in ("auto", "mineru")) else "pypdf2"
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
            return IndexResult(
                filename=filename, status="failed",
                error=(
                    f"文档解析后无内容 "
                    f"(引擎: {actual_engine}, 文件大小: {file_size} bytes). "
                    f"{'MinerU 已安装但解析失败，可能是扫描件PDF，可尝试 ocr=True' if _mineru_available else '建议安装 MinerU 增强解析: pip install magic-pdf'}"
                ),
            )

        chunks = split_documents(docs)
        if not chunks:
            return IndexResult(
                filename=filename, status="failed",
                error="文档分块后无内容",
            )

        count = add_documents(chunks)
        # 图谱构建改为后台线程执行，不阻塞索引 API 响应
        import threading
        threading.Thread(
            target=_try_build_graph, args=(chunks, filename),
            daemon=True,
        ).start()
        elapsed = (time.time() - start) * 1000

        logger.info(f"索引完成: {filename} → {count} chunks ({elapsed:.0f}ms)")
        return IndexResult(
            filename=filename, status="ok",
            chunks=count, elapsed_ms=elapsed,
        )

    except Exception as e:
        elapsed = (time.time() - start) * 1000
        logger.error(f"索引失败: {filename}: {e}")
        return IndexResult(
            filename=filename, status="failed",
            error=str(e), elapsed_ms=elapsed,
        )


def index_directory(
    directory: str,
    recursive: bool = True,
    force: bool = False,
    pdf_engine: str = "auto",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> BatchIndexResult:
    """
    批量索引目录下所有支持的文件。

    Args:
        directory: 目录路径
        recursive: 是否递归子目录
        force: 是否强制重建
        progress_callback: 进度回调 (current, total, filename)

    Returns:
        BatchIndexResult
    """
    start = time.time()
    result = BatchIndexResult()

    # 收集所有支持的文件
    supported_exts = {".pdf", ".docx", ".xlsx", ".xls", ".txt", ".csv"}
    files = []

    if recursive:
        for root, _, filenames in os.walk(directory, followlinks=False):
            for f in filenames:
                if Path(f).suffix.lower() in supported_exts:
                    files.append(os.path.join(root, f))
    else:
        for f in os.listdir(directory):
            full = os.path.join(directory, f)
            if os.path.isfile(full) and Path(f).suffix.lower() in supported_exts:
                files.append(full)

    result.total = len(files)
    logger.info(f"批量索引: 发现 {result.total} 个文件")

    for i, file_path in enumerate(files, 1):
        if progress_callback:
            progress_callback(i, result.total, Path(file_path).name)

        r = index_file(file_path, force=force, pdf_engine=pdf_engine)
        result.files.append(r)

        if r.status == "ok":
            result.indexed += 1
            result.total_chunks += r.chunks
        elif r.status == "skipped":
            result.skipped += 1
        else:
            result.failed += 1

        # 间隔输出进度
        if i % 10 == 0:
            logger.info(
                f"批量索引进度: {i}/{result.total} "
                f"(✅{result.indexed} ⏭{result.skipped} ❌{result.failed})"
            )

    result.elapsed_ms = (time.time() - start) * 1000
    logger.info(
        f"批量索引完成: {result.total} 文件 → {result.total_chunks} chunks "
        f"({result.elapsed_ms:.0f}ms)"
    )
    return result


def reindex_all(directory: str = "data/documents", pdf_engine: str = "auto") -> BatchIndexResult:
    """全量重建索引 — 清空知识库后重新索引目录"""
    from app.rag.store import reset_all_vector_indexes
    from app.rag.retriever import _invalidate_bm25_cache
    from app.rag.cache import query_cache
    logger.warning("全量重建索引：清空知识库...")
    reset_all_vector_indexes()
    # 清除查询缓存（避免返回旧文档结果）
    query_cache.clear()
    _invalidate_bm25_cache()
    # 清空图谱
    if settings.GRAPH_BACKEND == "lightrag":
        from app.rag.lightrag_store import get_lightrag_store
        store = get_lightrag_store()
        if store:
            store.clear_all()
    elif settings.GRAPH_BACKEND == "neo4j":
        neo4j_store = get_neo4j_store()
        if neo4j_store and neo4j_store.is_available():
            neo4j_store.clear_all()
    return index_directory(directory, recursive=True, force=True, pdf_engine=pdf_engine)


def _try_build_graph(chunks, filename: str):
    """尝试对 chunks 构建图谱（GRAPH_BACKEND 配置驱动）"""
    try:
        # 1. LightRAG（内存极速）
        if settings.GRAPH_BACKEND == "lightrag":
            from app.rag.lightrag_store import get_lightrag_store
            store = get_lightrag_store()
            if store and store.is_available():
                entities, relations = store.batch_extract_and_store(chunks)
                if entities > 0:
                    logger.info(f"LightRAG: {filename} → {entities} 实体, {relations} 关系")
                return

        # 2. Neo4j（持久化图谱）
        if settings.GRAPH_BACKEND == "neo4j":
            neo4j_store = get_neo4j_store()
            if neo4j_store and neo4j_store.is_available():
                entities, relations = neo4j_store.batch_extract_and_store(chunks)
                if entities > 0:
                    logger.info(f"Neo4j: {filename} → {entities} 实体, {relations} 关系")
    except Exception as e:
        logger.warning(f"图谱构建跳过 ({filename}): {e}")


def get_index_status() -> dict:
    """获取索引进度概览"""
    from app.rag.store import get_document_count, get_unique_sources
    import os

    docs_dir = "data/documents"
    physical_count = 0
    if os.path.exists(docs_dir):
        physical_count = sum(
            1 for f in os.listdir(docs_dir)
            if os.path.isfile(os.path.join(docs_dir, f))
            and Path(f).suffix.lower() in {".pdf", ".docx", ".xlsx", ".xls", ".txt", ".csv"}
        )

    indexed = set(get_unique_sources())
    all_files = set()
    if os.path.exists(docs_dir):
        all_files = {
            f for f in os.listdir(docs_dir)
            if os.path.isfile(os.path.join(docs_dir, f))
        }

    return {
        "chunks_total": get_document_count(),
        "files_physical": physical_count,
        "files_indexed": len(indexed),
        "files_unindexed": list(all_files - indexed),
        "indexed_sources": sorted(indexed),
    }
