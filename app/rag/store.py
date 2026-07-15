"""纯 RAG 的唯一知识库入口：PostgreSQL + pgvector。"""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document

from app.rag.errors import KnowledgeStoreUnavailable
from app.rag.pgvector_store import get_pgvector_store


def _store():
    store = get_pgvector_store()
    if store is None:
        raise KnowledgeStoreUnavailable("pgvector 知识库不可用")
    return store


def add_documents(documents: list[Document], batch_size: int = 50) -> int:
    """向唯一知识库批量写入切片。"""
    return _store().add_documents(documents, batch_size)


def delete_by_source(source: str) -> int:
    """删除原文件对应的全部切片。"""
    return _store().delete_by_source(source)


def get_document_count() -> int:
    try:
        return _store().get_document_count()
    except KnowledgeStoreUnavailable:
        return 0


def get_unique_sources() -> list[str]:
    try:
        return _store().get_unique_sources()
    except KnowledgeStoreUnavailable:
        return []


def get_document_summaries() -> list[dict]:
    """获取文档级的切片汇总，索引任务结束后用于确认入库结果。"""
    try:
        return _store().get_document_summaries()
    except KnowledgeStoreUnavailable:
        return []


def get_vector_search_results(
    query: str, k: int = 20, fetch_k: int = 30, filters: dict[str, Any] | None = None,
) -> list[Document]:
    """执行一次融合检索，不再叠加 BM25 或第二套向量数据库。"""
    return _store().search(query, k=k, fetch_k=fetch_k, filters=filters)


def get_evidence(document_id: str, chunk_id: str):
    """读取单条引用的完整证据与相邻上下文。"""
    return _store().get_evidence(document_id, chunk_id)


def resolve_document_path(document_id: str):
    """将公开文档身份解析为受控文件路径。"""
    return _store().resolve_document_path(document_id)


def clear_collection() -> None:
    """清空知识库切片，不删除原始文件。"""
    _store().clear_collection()
