"""纯 RAG 检索、引用和性能策略的回归测试。"""

import pytest
from langchain_core.documents import Document


def test_build_sources_keeps_each_evidence_chunk():
    """同一文件的不同页必须是可独立点击的证据。"""
    from app.rag.retriever import build_sources

    docs = [
        Document(
            page_content="第一条证据",
            metadata={"filename": "制度.pdf", "page": 1, "chunk_id": "chunk-1", "document_id": "doc-1"},
        ),
        Document(
            page_content="第二条证据",
            metadata={"filename": "制度.pdf", "page": 2, "chunk_id": "chunk-2", "document_id": "doc-1"},
        ),
    ]

    sources = build_sources(docs)

    assert [source["chunk_id"] for source in sources] == ["chunk-1", "chunk-2"]
    assert [source["page"] for source in sources] == [1, 2]
    assert [source["citation_id"] for source in sources] == ["S1", "S2"]


def test_filter_sources_only_keeps_citations_used_by_answer():
    """用户可见来源只能是最终回答实际采用的证据，不能泄漏召回候选。"""
    from app.rag.retriever import filter_sources_by_citations

    sources = [
        {"citation_id": "S1", "filename": "年休假办法.pdf"},
        {"citation_id": "S2", "filename": "商品明细.xlsx"},
        {"citation_id": "S3", "filename": "考勤制度.pdf"},
    ]

    accepted = filter_sources_by_citations("年休假按制度执行。[S1]", sources)

    assert accepted == [sources[0]]


@pytest.mark.asyncio
async def test_streaming_path_never_enables_online_rerank(monkeypatch):
    """线上流式问答默认跳过 CPU Cross-Encoder，避免二十秒级重排。"""
    from app.rag import retriever

    captured = {}

    async def fake_retrieve(question, k, history=None):
        from app.rag.query_plan import build_rule_plan

        captured.update({"question": question, "history": history})
        return [], 0, {"retrieval": 1.0, "query_plan": 0.0}, 1, build_rule_plan(question)

    monkeypatch.setattr(retriever, "_retrieve_with_query_plan", fake_retrieve)

    events = [event async for event in retriever.rag_qa_stream("年休假有几天？")]

    assert captured["history"] is None
    assert events[0]["type"] == "retrieval"


def test_rrf_fuses_once_and_uses_stable_chunk_identity():
    """向量和全文候选应单次 RRF 融合，不能使用内容前缀误去重。"""
    from app.rag.pgvector_store import reciprocal_rank_fusion

    vector = [
        {"chunk_id": "v1", "rank": 1},
        {"chunk_id": "shared", "rank": 2},
    ]
    keyword = [
        {"chunk_id": "shared", "rank": 1},
        {"chunk_id": "k1", "rank": 2},
    ]

    result = reciprocal_rank_fusion(vector, keyword)

    assert [item["chunk_id"] for item in result] == ["shared", "v1", "k1"]
    assert result[0]["score"] > result[1]["score"]
