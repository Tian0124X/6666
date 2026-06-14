# 2026 RAG 知识问答系统
#
# 核心链路:
#   Adaptive路由 → [缓存|标准RAG|Agentic RAG|GraphRAG Lite]
#
# 标准 RAG:  多查询扩展 → 混合检索(BM25+向量+RRF) → LLM重排序 → 反幻觉生成
# 缓存层:    Redis语义缓存 (40-60% LLM调用节省)
# Agentic:   检索→生成→幻觉检测→重检索→重生成 (自验证循环, ≤3轮)
# GraphRAG:  实体关系提取 → 多跳推理

from app.rag.loader import UniversalDocumentLoader
from app.rag.splitter import split_documents, create_chinese_splitter, PRESETS
from app.rag.embedder import BGEEmbeddings
from app.rag.store import (
    get_vector_store, add_documents, delete_by_source,
    get_unique_sources, clear_collection,
)
from app.rag.retriever import rag_qa
from app.rag.advanced import smart_rag_qa, graph_rag_qa, _agentic_retrieve_and_generate
from app.rag.cache import query_cache
from app.rag.indexer import index_file, index_directory, reindex_all, get_index_status

__all__ = [
    # 文档处理
    "UniversalDocumentLoader",
    "split_documents",
    "create_chinese_splitter",
    "PRESETS",
    # 向量化与存储
    "BGEEmbeddings",
    "get_vector_store",
    "add_documents",
    "delete_by_source",
    "get_unique_sources",
    "clear_collection",
    # 检索与问答
    "rag_qa",                    # 标准 RAG
    "smart_rag_qa",              # 自适应 RAG（推荐）
    "graph_rag_qa",              # GraphRAG Lite
    # 缓存
    "query_cache",
    # 索引管理
    "index_file",
    "index_directory",
    "reindex_all",
    "get_index_status",
]
