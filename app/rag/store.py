"""向量存储 — pgvector(主) + ChromaDB(备) 双后端

借鉴 MaxKB (pgvector) + Dify (统一DB): pgvector 生产级主力，ChromaDB 快速开发降级
"""

import logging
from typing import List, Optional

from langchain_chroma import Chroma
from langchain_core.documents import Document
from app.config import settings
from app.rag.embedder import BGEEmbeddings

logger = logging.getLogger(__name__)

# 向量后端优先级: pgvector > ChromaDB
_vector_backend: Optional[str] = None  # "pgvector" | "chromadb" | None


def _detect_backend() -> str:
    """检测可用的向量后端"""
    global _vector_backend
    if _vector_backend is not None:
        return _vector_backend

    # 尝试 pgvector
    try:
        from app.rag.pgvector_store import get_pgvector_store
        store = get_pgvector_store()
        if store and store.is_available():
            _vector_backend = "pgvector"
            logger.info("🎯 向量后端: pgvector (PostgreSQL)")
            return _vector_backend
    except Exception as e:
        logger.debug(f"pgvector 跳过: {e}")

    # 回退 ChromaDB
    _vector_backend = "chromadb"
    logger.info("🎯 向量后端: ChromaDB (回退)")
    return _vector_backend

COLLECTION_NAME = "enterprise_knowledge"

# HNSW 索引参数（2026 生产最佳实践）
# ChromaDB 底层使用 HNSW (Hierarchical Navigable Small World)
# 对比 IVF_FLAT: HNSW 查询快 3-5x，内存占用略高
HNSW_METADATA = {
    "hnsw:space": "cosine",            # 距离度量: cosine / l2 / ip
    "hnsw:construction_ef": 200,       # 构建精度 (默认100, 越大越精确但越慢)
    "hnsw:search_ef": 100,             # 查询精度 (默认10, 100 = 高精度模式)
    "hnsw:M": 32,                      # 每节点最大连接数 (默认16, 32 = 高召回)
    "hnsw:num_threads": 4,             # 构建并行线程数
    "hnsw:resize_factor": 2,           # 扩容因子
}

# 全局单例
_embedder: Optional[BGEEmbeddings] = None
_vector_store: Optional[Chroma] = None


def get_embedder() -> BGEEmbeddings:
    global _embedder
    if _embedder is None:
        logger.info("正在加载 BGE-Small-ZH 模型...")
        _embedder = BGEEmbeddings()
        logger.info(f"BGE 模型就绪 (维度: {_embedder.dimension})")
    return _embedder


def get_vector_store():
    """获取向量存储实例（懒加载单例，含 HNSW 索引配置）"""
    global _vector_store
    if _vector_store is None:
        from langchain_chroma import Chroma
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        _vector_store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=get_embedder(),
            collection_metadata=HNSW_METADATA,
            client=chromadb.HttpClient(
                host=settings.CHROMA_HOST,
                port=settings.CHROMA_PORT,
                settings=ChromaSettings(anonymized_telemetry=False),
            ),
        )
        logger.info(
            f"ChromaDB 连接就绪: {settings.chroma_url} "
            f"(HNSW: M={HNSW_METADATA['hnsw:M']}, "
            f"ef_construction={HNSW_METADATA['hnsw:construction_ef']}, "
            f"ef_search={HNSW_METADATA['hnsw:search_ef']})"
        )
    return _vector_store


def add_documents(documents: List[Document], batch_size: int = 50) -> int:
    """批量添加文档到向量库。pgvector 主 → ChromaDB 备。"""
    backend = _detect_backend()

    if backend == "pgvector":
        from app.rag.pgvector_store import get_pgvector_store
        store = get_pgvector_store()
        if store:
            return store.add_documents(documents, batch_size)

    # ChromaDB 回退
    store = get_vector_store()
    total = 0
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        store.add_documents(batch)
        total += len(batch)
    logger.info(f"ChromaDB 已添加 {total} 个 chunks")
    return total


def delete_by_source(source: str) -> int:
    """按源文件路径删除文档"""
    backend = _detect_backend()
    if backend == "pgvector":
        from app.rag.pgvector_store import get_pgvector_store
        store = get_pgvector_store()
        if store:
            return store.delete_by_source(source)

    store = get_vector_store()
    results = store.get(where={"source": source})
    ids = results.get("ids", [])
    if ids:
        store.delete(ids=ids)
        logger.info(f"已删除 {len(ids)} 个 chunks (source={source})")
    return len(ids)


def get_document_count() -> int:
    """获取知识库中的文档 chunk 总数"""
    backend = _detect_backend()
    if backend == "pgvector":
        from app.rag.pgvector_store import get_pgvector_store
        store = get_pgvector_store()
        if store:
            return store.get_document_count()

    try:
        store = get_vector_store()
        return store._collection.count()
    except Exception as e:
        logger.warning(f"获取文档数失败: {e}")
        return 0


def get_unique_sources() -> List[str]:
    """获取知识库中所有不重复的源文件"""
    backend = _detect_backend()
    if backend == "pgvector":
        from app.rag.pgvector_store import get_pgvector_store
        store = get_pgvector_store()
        if store:
            return store.get_unique_sources()

    try:
        store = get_vector_store()
        results = store.get()
        sources = set()
        for meta in results.get("metadatas", []):
            if meta and "filename" in meta:
                sources.add(meta["filename"])
        return sorted(sources)
    except Exception as e:
        logger.warning(f"获取源文件列表失败: {e}")
        return []


def clear_collection():
    """清空整个知识库"""
    backend = _detect_backend()
    if backend == "pgvector":
        from app.rag.pgvector_store import get_pgvector_store
        store = get_pgvector_store()
        if store:
            store.clear_collection()
            return

    try:
        store = get_vector_store()
        count = store._collection.count()
        if count > 0:
            page_size = 500
            deleted = 0
            for offset in range(0, count, page_size):
                batch = store.get(limit=page_size, offset=offset)
                ids = batch.get("ids", [])
                if ids:
                    store.delete(ids=ids)
                    deleted += len(ids)
            logger.warning(f"已清空知识库 ({deleted} 个 chunks)")
    except Exception as e:
        logger.warning(f"清空知识库失败: {e}")
