"""QueryPlan、过滤检索和受控多路召回的回归测试。"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document


def _doc(chunk_id: str, document_id: str, filename: str = "制度.pdf") -> Document:
    """构造带稳定切片身份的检索候选。"""
    return Document(
        page_content=f"证据 {chunk_id}",
        metadata={"chunk_id": chunk_id, "document_id": document_id, "filename": filename},
    )


def test_extract_explicit_filters_keeps_filename_page_sheet_and_type():
    """文件、页码和 Sheet 必须来自用户原问题。"""
    from app.rag.query_plan import extract_explicit_filters

    filters = extract_explicit_filters("请查 商品数据.xlsx 的第3页到第5页，Sheet: 销售明细，xlsx 文件")

    assert filters.filenames == ("商品数据.xlsx",)
    assert (filters.page_start, filters.page_end) == (3, 5)
    assert filters.sheet == "销售明细"
    assert filters.file_types == ("xlsx",)


def test_extract_explicit_filters_keeps_manual_document_date_range():
    """时间条件只能解析为明确的 ISO 区间，供已标注日期的文档过滤使用。"""
    from app.rag.query_plan import extract_explicit_filters

    filters = extract_explicit_filters("查询 2025年3月到2025年4月 发布的员工制度")

    assert filters.document_date_start == "2025-03-01"
    assert filters.document_date_end == "2025-04-30"
    assert filters.to_store_filters()["document_date_start"] == "2025-03-01"


def test_rule_variants_cover_reviewed_domain_synonyms_without_llm():
    """领域同义改写必须是确定性的，且不依赖模型调用。"""
    from app.rag.query_plan import build_rule_plan

    plan = build_rule_plan("新员工需要在入职多少天内提交累计工龄证明？")

    assert plan.source == "rules"
    assert plan.variants == ["新入职员工累计工龄佐证材料提交期限"]


def test_rule_variants_cover_annual_leave_abbreviation_without_llm():
    """制度常用全称为年休假时，口语化年假不能被错误召回到无关表格。"""
    from app.rag.query_plan import build_rule_plan

    plan = build_rule_plan("年假申请的审批顺序是什么？")

    assert plan.variants == ["年休假申请的审批顺序是什么？"]


@pytest.mark.asyncio
async def test_normal_question_does_not_call_llm_when_candidates_are_sufficient(monkeypatch):
    """独立问题候选充分时只能进行一次规则检索。"""
    from app.rag import retriever

    calls = {"search": 0, "llm": 0}

    async def fake_search(plan, k):
        calls["search"] += 1
        return [_doc("a1", "a"), _doc("b1", "b"), _doc("c1", "c")], 3

    async def fake_llm(question, history, base_plan):
        calls["llm"] += 1
        return base_plan

    monkeypatch.setattr(retriever, "_search_query_plan", fake_search)
    monkeypatch.setattr(retriever, "build_llm_plan", fake_llm)

    _, _, _, query_count, plan = await retriever._retrieve_with_query_plan("年休假有几天？", 5)

    assert calls == {"search": 1, "llm": 0}
    assert query_count == 1
    assert plan.source == "rules"


def test_long_question_without_term_support_is_weak_signal():
    """长问题即使候选数量够，也要检查候选是否实际覆盖关键语义。"""
    from app.rag.retriever import _has_sufficient_evidence_support

    docs = [_doc("a1", "a"), _doc("b1", "b"), _doc("c1", "c")]
    assert not _has_sufficient_evidence_support("新员工入职后多久内提交累计工龄证明", docs)


@pytest.mark.asyncio
async def test_follow_up_uses_llm_plan_but_keeps_explicit_filters(monkeypatch):
    """追问允许改写问题，但不能放宽用户指定的页码。"""
    from app.rag import retriever
    from app.rag.query_plan import QueryPlan

    captured = {}

    async def fake_llm(question, history, base_plan):
        return QueryPlan(
            original_query=question,
            canonical_query="员工带薪年休假资格",
            variants=["年假申请条件"],
            filters=base_plan.filters,
            source="llm",
        )

    async def fake_search(plan, k):
        captured["filters"] = plan.filters.to_store_filters()
        return [_doc("a1", "a")], 1

    monkeypatch.setattr(retriever, "build_llm_plan", fake_llm)
    monkeypatch.setattr(retriever, "_search_query_plan", fake_search)

    _, _, _, query_count, plan = await retriever._retrieve_with_query_plan("这个第3页怎么说？", 5, [{"role": "user", "content": "年假制度"}])

    assert query_count == 2
    assert plan.source == "llm"
    assert captured["filters"] == {"page_start": 3, "page_end": 3}


@pytest.mark.asyncio
async def test_invalid_llm_payload_falls_back_and_preserves_filters(monkeypatch):
    """模型返回非 JSON 时必须回退，且显式文件条件仍然保留。"""
    from app.config import settings
    from app.rag import query_plan

    class FakePrompt:
        def __or__(self, _llm):
            return self

        async def ainvoke(self, _values):
            return type("Response", (), {"content": "不是 JSON"})()

    monkeypatch.setattr(settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(query_plan.ChatPromptTemplate, "from_template", lambda _template: FakePrompt())
    base_plan = query_plan.build_rule_plan("《员工手册.pdf》第2页的规则")

    plan = await query_plan.build_llm_plan(base_plan.original_query, [], base_plan)

    assert plan.source == "fallback"
    assert plan.filters.to_store_filters() == {"filenames": ["员工手册.pdf"], "page_start": 2, "page_end": 2}


@pytest.mark.asyncio
async def test_llm_rewrite_cannot_change_exact_business_identifier(monkeypatch):
    """SP 编号等精确条件一旦被模型改写，必须回退原问题。"""
    from app.config import settings
    from app.rag import query_plan

    class FakePrompt:
        def __or__(self, _llm):
            return self

        async def ainvoke(self, _values):
            return type("Response", (), {"content": '{"canonical_query":"SP0001 的库存","variants":[]}'})()

    monkeypatch.setattr(settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(query_plan.ChatPromptTemplate, "from_template", lambda _template: FakePrompt())
    base_plan = query_plan.build_rule_plan("SP0003 的库存是多少")

    plan = await query_plan.build_llm_plan(base_plan.original_query, [], base_plan)

    assert plan.source == "fallback"
    assert plan.fallback_reason == "ValueError"
    assert plan.canonical_query == "SP0003 的库存是多少"


def test_parameterized_filter_clause_never_interpolates_user_values():
    """SQL 结构固定，用户输入只能作为数据库参数传递。"""
    from app.rag.pgvector_store import PGVectorStore

    clause, params = PGVectorStore._build_filter_clause({
        "filenames": ["制度'; DROP TABLE vector_documents; --.pdf"],
        "page_start": 2,
        "page_end": 4,
        "sheet": "销售明细",
        "file_types": ["xlsx"],
        "document_date_start": "2025-01-01",
        "document_date_end": "2025-12-31",
    })

    assert "DROP TABLE" not in clause
    assert "filename = %s" in clause
    assert "filename ILIKE %s" in clause
    assert "BETWEEN %s AND %s" in clause
    assert params[0] == "制度'; DROP TABLE vector_documents; --.pdf"
    assert "%制度'; DROP TABLE vector\\_documents; --.pdf%" in params
    assert params[-6:] == [2, 4, "销售明细", ["xlsx"], "2025-01-01", "2025-12-31"]


def test_filename_with_chinese_brackets_is_preserved():
    """文件名自身的中文方括号不能被错误删除。"""
    from app.rag.query_plan import extract_explicit_filters

    filters = extract_explicit_filters("《【公司官方政策】员工带薪年休假管理办法（RAG知识库专用）.pdf》第3页")

    assert filters.filenames == ("【公司官方政策】员工带薪年休假管理办法（RAG知识库专用）.pdf",)


def test_filename_filter_also_matches_the_uploaded_name_stem():
    """用户省略上传前后缀时，仍以文件主体名受控过滤。"""
    from app.rag.pgvector_store import PGVectorStore

    _, params = PGVectorStore._build_filter_clause({"filenames": ["商品数据明细.xlsx"]})

    assert "%商品数据明细%" in params


def test_multi_query_rrf_deduplicates_and_applies_document_cap(monkeypatch):
    """多路检索的重复块和单文档挤占必须在最终证据前被消除。"""
    from app.config import settings
    from app.rag.retriever import _fuse_query_results, _limit_document_candidates

    monkeypatch.setattr(settings, "RAG_QUERY_PLAN_DOCUMENT_CAP", 2)
    fused = _fuse_query_results([
        [_doc("a1", "doc-a"), _doc("a2", "doc-a"), _doc("a3", "doc-a"), _doc("b1", "doc-b")],
        [_doc("b1", "doc-b"), _doc("b2", "doc-b"), _doc("a3", "doc-a")],
    ])
    selected = _limit_document_candidates(fused, 5)

    assert len({doc.metadata["chunk_id"] for doc in fused}) == len(fused)
    assert sum(doc.metadata["document_id"] == "doc-a" for doc in selected) <= 2
    assert sum(doc.metadata["document_id"] == "doc-b" for doc in selected) <= 2


@pytest.mark.asyncio
async def test_stream_keeps_query_plan_candidates_internal(monkeypatch):
    """SSE 只能公开最终引用，不能公开 QueryPlan 候选。"""
    from app.rag import retriever
    from app.rag.query_plan import build_rule_plan

    async def fake_retrieve(question, k, history=None):
        return [_doc("a1", "doc-a")], 1, {"retrieval": 1.0, "query_plan": 0.0}, 1, build_rule_plan(question)

    monkeypatch.setattr(retriever, "_retrieve_with_query_plan", fake_retrieve)
    monkeypatch.setattr(retriever.settings, "LLM_API_KEY", "")

    events = [event async for event in retriever.rag_qa_stream("年休假有几天？")]

    assert events[0]["type"] == "retrieval"
    assert events[0]["sources"] == []


@pytest.mark.asyncio
async def test_non_stream_retrieved_count_keeps_legacy_final_document_semantics(monkeypatch):
    """非流式接口不能把内部候选数误报为最终返回切片数。"""
    from app.rag import retriever
    from app.rag.query_plan import build_rule_plan

    async def fake_retrieve(question, k, history=None):
        return [_doc("a1", "doc-a"), _doc("b1", "doc-b")], 9, {"retrieval": 1.0}, 1, build_rule_plan(question)

    monkeypatch.setattr(retriever, "_retrieve_with_query_plan", fake_retrieve)

    _, count, _, _ = await retriever._retrieve_final_documents("测试", 5, False, False)

    assert count == 2


def test_identifier_terms_are_kept_for_exact_structured_retrieval():
    """商品 ID 等业务标识符不能在中文分词阶段丢失。"""
    from app.rag.pgvector_store import PGVectorStore

    assert PGVectorStore._identifier_terms("查询 SP0004 和 ab-12 的库存") == ["SP0004", "AB-12"]
    assert PGVectorStore._identifier_terms("年休假有几天") == []
