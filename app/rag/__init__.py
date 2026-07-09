# 2026 RAG ??????
#
# ????:
#   Adaptive?? -> [??|??RAG|Agentic RAG|GraphRAG Lite]
#
# ?? RAG:  ????? -> ????(BM25+??+RRF) -> LLM??? -> ?????
# ???:    Redis???? (40-60% LLM????)
# Agentic:   ??->??->????->???->???(????? <=3?)
# GraphRAG:  ?????? -> ????
from app.rag.loader import UniversalDocumentLoader
from app.rag.splitter import split_documents, create_chinese_splitter, PRESETS
from app.rag.embedder import BGEEmbeddings
from app.rag.store import (
    get_vector_store, add_documents, delete_by_source,
    get_unique_sources, clear_collection,
)
from app.rag.retriever import rag_qa, build_sources
from app.rag.advanced import smart_rag_qa, graph_rag_qa, _agentic_retrieve_and_generate
from app.rag.cache import query_cache
from app.rag.indexer import index_file, index_directory, reindex_all, get_index_status
from app.rag.neo4j_store import Neo4jStore, get_neo4j_store
from app.rag.graph_retriever import graph_enhanced_retrieve
from app.rag.graph_extractor import batch_extract_entities, extract_query_entities, build_graph_context
from app.rag.lightrag_store import LightRAGStore, get_lightrag_store

__all__ = [
    # 鏂囨。澶勭悊
    "UniversalDocumentLoader",
    "split_documents",
    "create_chinese_splitter",
    "PRESETS",
    # 鍚戦噺鍖栦笌瀛樺偍
    "BGEEmbeddings",
    "get_vector_store",
    "add_documents",
    "delete_by_source",
    "get_unique_sources",
    "clear_collection",
# 检索与问答
    "rag_qa",                    # 鏍囧噯 RAG
    "smart_rag_qa",              # 自适应 RAG（推荐）
    "graph_rag_qa",              # GraphRAG Lite
    # 缂撳瓨
    "query_cache",
    # 绱㈠紩绠＄悊
    "index_file",
    "index_directory",
    "reindex_all",
    "get_index_status",
    # 图谱存储
    "Neo4jStore",
    "get_neo4j_store",
    "LightRAGStore",
    "get_lightrag_store",
]

