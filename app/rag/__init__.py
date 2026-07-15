"""知识库 RAG 核心模块。"""

from app.rag.embedder import BGEEmbeddings
from app.rag.loader import UniversalDocumentLoader
from app.rag.retriever import build_sources, rag_qa, rag_qa_stream
from app.rag.splitter import create_chinese_splitter, split_documents
from app.rag.store import add_documents, delete_by_source, get_unique_sources

__all__ = [
    "BGEEmbeddings", "UniversalDocumentLoader", "add_documents", "build_sources",
    "create_chinese_splitter", "delete_by_source", "get_unique_sources", "rag_qa",
    "rag_qa_stream", "split_documents",
]
