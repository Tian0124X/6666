"""向量库统一入口：pgvector 为主，ChromaDB 作为回退。"""

import logging
from typing import Callable, List, Optional

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.config import settings
from app.rag.embedder import BGEEmbeddings, get_embedding_model
from app.rag.errors import KnowledgeStoreUnavailable

logger = logging.getLogger(__name__)

COLLECTION_NAME = "enterprise_knowledge"
HNSW_METADATA = {
    "hnsw:space": "cosine",
    "hnsw:construction_ef": 200,
    "hnsw:search_ef": 100,
    "hnsw:M": 32,
    "hnsw:num_threads": 4,
    "hnsw:resize_factor": 2,
}

_vector_backend: Optional[str] = None
_embedder: Optional[BGEEmbeddings] = None
_vector_store: Optional[Chroma] = None


def get_embedder() -> BGEEmbeddings:
    global _embedder
    if _embedder is None:
        _embedder = get_embedding_model()
    return _embedder


def _create_chroma_client():
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    return chromadb.HttpClient(
        host=settings.CHROMA_HOST,
        port=settings.CHROMA_PORT,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def _reset_vector_store() -> None:
    global _vector_store
    _vector_store = None


def get_vector_store() -> Chroma:
    global _vector_store
    if _vector_store is None:
        _vector_store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=get_embedder(),
            collection_metadata=HNSW_METADATA,
            client=_create_chroma_client(),
        )
    return _vector_store


def _detect_backend() -> str:
    """返回健康后端；应用启动早于 Docker 就绪时允许 pgvector 恢复。"""
    global _vector_backend
    try:
        from app.rag.pgvector_store import get_pgvector_store

        pg = get_pgvector_store()
        if pg and pg.is_available():
            _vector_backend = "pgvector"
            return _vector_backend
    except Exception as exc:
        logger.debug("pgvector unavailable: %s", exc)

    try:
        get_vector_store()._collection.count()
        _vector_backend = "chromadb"
        return _vector_backend
    except Exception as exc:
        _vector_backend = None
        raise KnowledgeStoreUnavailable("Neither pgvector nor ChromaDB is available") from exc


def _chroma_op_with_retry(operation: Callable, *args, max_retries: int = 2):
    for attempt in range(max_retries):
        try:
            return operation(get_vector_store(), *args)
        except Exception:
            _reset_vector_store()
            if attempt == max_retries - 1:
                raise


def add_documents(documents: List[Document], batch_size: int = 50) -> int:
    backend = _detect_backend()
    if backend == "pgvector":
        from app.rag.pgvector_store import get_pgvector_store

        pg = get_pgvector_store()
        if pg:
            return pg.add_documents(documents, batch_size)

    def add_batches(store: Chroma, docs: List[Document], size: int) -> int:
        for offset in range(0, len(docs), size):
            store.add_documents(docs[offset:offset + size])
        return len(docs)

    try:
        return _chroma_op_with_retry(add_batches, documents, batch_size)
    except Exception as exc:
        raise KnowledgeStoreUnavailable("ChromaDB add failed") from exc


def delete_by_source(source: str) -> int:
    backend = _detect_backend()
    if backend == "pgvector":
        from app.rag.pgvector_store import get_pgvector_store

        pg = get_pgvector_store()
        if pg:
            return pg.delete_by_source(source)

    def delete_source(store: Chroma, value: str) -> int:
        result = store.get(where={"source": value})
        ids = result.get("ids", [])
        if ids:
            store.delete(ids=ids)
        return len(ids)

    try:
        return _chroma_op_with_retry(delete_source, source)
    except Exception as exc:
        raise KnowledgeStoreUnavailable("ChromaDB delete failed") from exc


def get_document_count() -> int:
    try:
        if _detect_backend() == "pgvector":
            from app.rag.pgvector_store import get_pgvector_store

            pg = get_pgvector_store()
            return pg.get_document_count() if pg else 0
        return get_vector_store()._collection.count()
    except KnowledgeStoreUnavailable:
        return 0


def get_unique_sources() -> List[str]:
    try:
        if _detect_backend() == "pgvector":
            from app.rag.pgvector_store import get_pgvector_store

            pg = get_pgvector_store()
            return pg.get_unique_sources() if pg else []
        result = get_vector_store().get(include=["metadatas"])
        return sorted({meta.get("filename", "") for meta in result.get("metadatas", []) if meta})
    except KnowledgeStoreUnavailable:
        return []


def clear_collection() -> None:
    """删除 ChromaDB collection，不影响原始文档。"""
    try:
        _create_chroma_client().delete_collection(COLLECTION_NAME)
    except Exception as exc:
        if "does not exist" not in str(exc).lower():
            raise KnowledgeStoreUnavailable("Unable to delete ChromaDB collection") from exc
    finally:
        _reset_vector_store()


def reset_all_vector_indexes() -> None:
    """嵌入模型迁移时，直接清空两套向量后端。"""
    from app.rag.pgvector_store import get_pgvector_store

    pg = get_pgvector_store()
    if not pg:
        raise KnowledgeStoreUnavailable("pgvector is required for a full index rebuild")
    pg.reset_for_embedding_migration()
    clear_collection()


def get_all_documents_for_bm25(limit: int = 5000) -> List[Document]:
    backend = _detect_backend()
    if backend == "pgvector":
        from app.rag.pgvector_store import get_pgvector_store

        pg = get_pgvector_store()
        return pg.get_all_documents(limit=limit) if pg else []

    try:
        store = get_vector_store()
        total = min(store._collection.count(), limit)
        docs: List[Document] = []
        for offset in range(0, total, 500):
            result = store.get(limit=min(500, total - offset), offset=offset)
            for index, content in enumerate(result.get("documents", [])):
                metadata = result.get("metadatas", [{}])[index] if result.get("metadatas") else {}
                docs.append(Document(page_content=content, metadata=metadata))
        return docs
    except Exception as exc:
        raise KnowledgeStoreUnavailable("ChromaDB document scan failed") from exc


def get_vector_search_results(query: str, k: int = 20, fetch_k: int = 60) -> List[Document]:
    backend = _detect_backend()
    if backend == "pgvector":
        from app.rag.pgvector_store import get_pgvector_store

        pg = get_pgvector_store()
        if pg:
            return pg.search(query, k=k, fetch_k=fetch_k)

    try:
        retriever = get_vector_store().as_retriever(
            search_type="mmr",
            search_kwargs={"k": k, "fetch_k": fetch_k, "lambda_mult": 0.7},
        )
        return retriever.invoke(query)
    except Exception as exc:
        raise KnowledgeStoreUnavailable("ChromaDB vector search failed") from exc
