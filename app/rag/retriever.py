"""纯 RAG 问答链路：改写、单次召回、引用生成与过程追踪。"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections import defaultdict
from typing import Iterable

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

from app.config import settings
from app.rag.errors import KnowledgeStoreUnavailable
from app.rag.query_plan import QueryPlan, build_llm_plan, build_rule_plan, is_follow_up
from app.rag.llm_factory import get_llm
from app.rag.store import get_vector_search_results

logger = logging.getLogger(__name__)

RAG_SYSTEM_PROMPT = """你是“知识库 RAG”。必须严格依据给定证据回答。

规则：
1. 不要编造证据中不存在的事实。
2. 每个关键结论后必须使用 [S1]、[S2] 这类引用标记。
3. 若证据不足，直接回答“资料不足，无法依据当前知识库确认。”，即“我无法回答”。
4. 只使用给出的引用编号，不能创造新的编号。
"""
RAG_USER_PROMPT = """用户问题：{question}

可用证据：
{context}

请输出简洁、可核查的回答。"""
QUERY_EXPANSION_PROMPT = ChatPromptTemplate.from_template(
    """为下列问题生成 3 个不同表达的检索查询，每行一个，不要编号。
问题：{question}"""
)


def _chinese_tokenize(text: str) -> list[str]:
    """为离线评测保留中文分词能力。"""
    try:
        import jieba
        tokens = list(jieba.cut(text))
        if len(tokens) == 1 and len(text.strip()) > 1:
            return list(text)
        return tokens
        # 单个未登录词不能支撑关键词召回，退化为字符级 token。
        return list(text) if len(tokens) == 1 and len(text.strip()) > 1 else tokens
    except ImportError:
        if len(text.strip()) > 1 and " " not in text.strip():
            return list(text)
        return [part for part in re.split(r"\s+", text) if part] or list(text)


def build_sources(docs: Iterable[Document]) -> list[dict]:
    """将每个最终切片转换为独立、可点击的证据。"""
    sources: list[dict] = []
    seen: set[str] = set()
    for index, doc in enumerate(docs, start=1):
        metadata = doc.metadata
        document_id = str(metadata.get("document_id") or metadata.get("source") or "unknown")
        chunk_id = str(metadata.get("chunk_id") or f"{document_id}:{metadata.get('page', '')}:{index}")
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        sources.append({
            "citation_id": f"S{len(sources) + 1}",
            "document_id": document_id,
            "chunk_id": chunk_id,
            "filename": metadata.get("filename", "未命名文档"),
            "page": metadata.get("page"),
            "chunk_index": metadata.get("chunk_index"),
            "excerpt": doc.page_content[:240],
            "score": metadata.get("score"),
        })
    return sources


def _format_context(docs: list[Document]) -> str:
    """按证据预算组织上下文，并保留与 UI 一致的引用编号。"""
    sources = build_sources(docs)
    parts = []
    for source, doc in zip(sources, docs):
        location = source["filename"]
        if source["page"] is not None:
            location += f"，第{source['page']}页"
        parts.append(f"[{source['citation_id']}] {location}\n{doc.page_content[:1200]}")
    return "\n\n---\n\n".join(parts)


def _fallback_answer(sources: list[dict]) -> str:
    if not sources:
        return "资料不足，无法依据当前知识库确认。"
    source_list = "、".join(f"[{source['citation_id']}]" for source in sources[:3])
    return f"已找到与问题相关的知识库证据，请查看引用来源：{source_list}"


def _validate_citations(answer: str, sources: list[dict]) -> str:
    """拒绝无效引用；无有效引文时返回可核查的保守答复。"""
    valid = {source["citation_id"] for source in sources}
    used = set(re.findall(r"\[(S\d+)\]", answer))
    if not used or not used.issubset(valid):
        return _fallback_answer(sources)
    return answer.strip()


def filter_sources_by_citations(answer: str, sources: list[dict]) -> list[dict]:
    """只保留最终答案确实引用的切片，候选文档不会暴露到用户界面。"""
    cited_ids = set(re.findall(r"\[(S\d+)\]", answer))
    return [source for source in sources if source["citation_id"] in cited_ids]


async def _hybrid_search(
    query: str, k: int = 20, filters: dict | None = None,
) -> list[Document]:
    """兼容评测接口；内部只执行 pgvector 的单次融合检索。"""
    return await asyncio.to_thread(get_vector_search_results, query, k, max(30, k), filters)


def _chunk_identity(doc: Document, fallback_index: int) -> str:
    """以数据库切片身份去重，缺失时才退化为稳定位置身份。"""
    metadata = doc.metadata
    return str(
        metadata.get("chunk_id")
        or f"{metadata.get('document_id') or metadata.get('source') or metadata.get('filename', 'unknown')}:{metadata.get('chunk_index', fallback_index)}"
    )


def _fuse_query_results(ranked_results: list[list[Document]]) -> list[Document]:
    """对主问题和有限变体做加权 RRF，主问题始终拥有最高权重。"""
    by_chunk: dict[str, Document] = {}
    scores: defaultdict[str, float] = defaultdict(float)
    for query_index, docs in enumerate(ranked_results):
        weight = 1.0 if query_index == 0 else 0.65
        for position, doc in enumerate(docs, start=1):
            chunk_id = _chunk_identity(doc, position)
            by_chunk.setdefault(chunk_id, doc)
            scores[chunk_id] += weight / (60 + position)
    fused: list[Document] = []
    for chunk_id in sorted(by_chunk, key=lambda item: (-scores[item], item)):
        original = by_chunk[chunk_id]
        metadata = dict(original.metadata)
        metadata["score"] = round(scores[chunk_id], 8)
        fused.append(Document(page_content=original.page_content, metadata=metadata))
    return fused


def _limit_document_candidates(docs: list[Document], k: int) -> list[Document]:
    """防止同一文档的相邻切片挤占最终证据位。"""
    selected: list[Document] = []
    per_document: defaultdict[str, int] = defaultdict(int)
    seen_chunks: set[str] = set()
    cap = max(1, settings.RAG_QUERY_PLAN_DOCUMENT_CAP)
    for index, doc in enumerate(docs, start=1):
        chunk_id = _chunk_identity(doc, index)
        document_key = str(
            doc.metadata.get("document_id") or doc.metadata.get("source") or doc.metadata.get("filename") or "unknown"
        )
        if chunk_id in seen_chunks or per_document[document_key] >= cap:
            continue
        seen_chunks.add(chunk_id)
        per_document[document_key] += 1
        selected.append(doc)
        if len(selected) >= k:
            break
    return selected


async def _search_query_plan(plan: QueryPlan, k: int) -> tuple[list[Document], int]:
    """并行检索主问题与变体；任一变体失败时由调用方回退规则计划。"""
    queries = plan.queries
    search_k = max(k, settings.RAG_SEARCH_K)
    results = await asyncio.gather(
        *[_hybrid_search(query, search_k, plan.filters.to_store_filters()) for query in queries],
        return_exceptions=True,
    )
    failures = [result for result in results if isinstance(result, Exception)]
    if failures:
        if isinstance(failures[0], KnowledgeStoreUnavailable):
            raise failures[0]
        raise RuntimeError(f"QueryPlan 检索失败: {type(failures[0]).__name__}") from failures[0]
    ranked_results = [result for result in results if isinstance(result, list)]
    fused = _fuse_query_results(ranked_results)
    return _limit_document_candidates(fused, k), len(fused)


def _log_query_trace(trace_id: str, plan: QueryPlan, candidate_count: int, timings: dict[str, float]) -> None:
    """只写入内部结构化摘要，不向 SSE 或用户界面泄漏候选与规划正文。"""
    logger.info(
        "rag_query_trace=%s",
        json.dumps(
            {
                "trace_id": trace_id,
                "plan": plan.trace_summary(),
                "candidate_count": candidate_count,
                "timings_ms": timings,
            },
            ensure_ascii=False,
        ),
    )


async def _retrieve_with_query_plan(
    question: str, k: int, history: list[dict] | None = None,
) -> tuple[list[Document], int, dict[str, float], int, QueryPlan]:
    """按需生成 QueryPlan，并保证任一异常都回退到规则单路检索。"""
    started = time.perf_counter()
    base_plan = build_rule_plan(question)
    plan = base_plan
    trace_id = str(uuid.uuid4())
    try:
        if not settings.RAG_QUERY_PLAN_ENABLED:
            plan.source = "disabled"
            docs, candidate_count = await _search_query_plan(plan, k)
        elif is_follow_up(question):
            plan = await build_llm_plan(question, history, base_plan)
            docs, candidate_count = await _search_query_plan(plan, k)
        else:
            docs, candidate_count = await _search_query_plan(base_plan, k)
            if candidate_count < max(1, settings.RAG_QUERY_PLAN_MIN_CANDIDATES):
                plan = await build_llm_plan(question, history, base_plan)
                if plan.source == "llm" and len(plan.queries) > 1:
                    docs, candidate_count = await _search_query_plan(plan, k)
    except KnowledgeStoreUnavailable:
        raise
    except Exception as exc:
        # 回退时保留原问题的显式过滤，不能为了“有结果”而扩大范围。
        plan = build_rule_plan(question)
        plan.source = "fallback"
        plan.fallback_reason = type(exc).__name__
        docs, candidate_count = await _search_query_plan(plan, k)
    timings = {
        "query_plan": plan.planning_ms,
        "expansion": 0.0,
        "retrieval": round((time.perf_counter() - started) * 1000, 1),
        "rerank": 0.0,
    }
    timings["total_retrieval"] = timings["retrieval"]
    _log_query_trace(trace_id, plan, candidate_count, timings)
    return docs, candidate_count, timings, len(plan.queries), plan


def _cross_encoder_rerank(question: str, docs: list[Document], top_n: int = 5) -> list[Document]:
    """默认不在线重排；仅在显式配置后由评测或 GPU 环境接管。"""
    return docs[:top_n]


def _llm_rerank(question: str, docs: list[Document], top_n: int = 5) -> list[Document]:
    """保留评测兼容入口，线上默认不调用。"""
    return _cross_encoder_rerank(question, docs, top_n)


async def _retrieve_final_documents(
    question: str, k: int, use_expansion: bool, use_rerank: bool
) -> tuple[list[Document], int, dict[str, float], int]:
    """测量纯 RAG 检索阶段；查询扩展和在线重排默认关闭。"""
    docs, candidate_count, timings, query_count, _ = await _retrieve_with_query_plan(question, k)
    if use_rerank and settings.RAG_ONLINE_RERANK:
        rerank_started = time.perf_counter()
        docs = await asyncio.to_thread(_cross_encoder_rerank, question, docs, k)
        timings["rerank"] = round((time.perf_counter() - rerank_started) * 1000, 1)
    # 非流式旧接口的 retrieved_count 一直表示最终返回切片数，不暴露内部候选数。
    return docs, len(docs), timings, query_count


async def _generate_answer_async(question: str, docs: list[Document]) -> tuple[str, list[dict]]:
    sources = build_sources(docs)
    if not docs or not settings.is_llm_available:
        answer = _fallback_answer(sources)
        return answer, filter_sources_by_citations(answer, sources)
    chain = ChatPromptTemplate.from_messages([
        ("system", RAG_SYSTEM_PROMPT), ("user", RAG_USER_PROMPT),
    ]) | get_llm(temperature=0.1)
    try:
        response = await chain.ainvoke({"question": question, "context": _format_context(docs)})
        answer = _validate_citations(str(response.content), sources)
        return answer, filter_sources_by_citations(answer, sources)
    except Exception:
        answer = _fallback_answer(sources)
        return answer, filter_sources_by_citations(answer, sources)


async def rag_qa(
    question: str, k: int = 5, use_expansion: bool = False, use_rerank: bool = False
) -> dict:
    """非流式纯 RAG 问答入口。"""
    started = time.perf_counter()
    docs, count, timings, query_count = await _retrieve_final_documents(question, k, use_expansion, use_rerank)
    generation_started = time.perf_counter()
    answer, sources = await _generate_answer_async(question, docs)
    timings["generation"] = round((time.perf_counter() - generation_started) * 1000, 1)
    timings["total"] = round((time.perf_counter() - started) * 1000, 1)
    return {
        "answer": answer, "sources": sources, "retrieved_count": count,
        "query_count": query_count, "timings_ms": timings,
    }


async def rag_qa_stream(question: str, k: int = 5, history: list[dict] | None = None):
    """先发送可点击证据，再逐 token 输出带引用回答。"""
    started = time.perf_counter()
    docs, count, timings, query_count, plan = await _retrieve_with_query_plan(question, k, history)
    rewritten = plan.canonical_query
    timings["query_rewrite"] = plan.planning_ms
    timings["total_retrieval"] = round((time.perf_counter() - started) * 1000, 1)
    candidate_sources = build_sources(docs)
    yield {
        # 候选仅用于展示过程数量，避免把未采纳文档误导为回答依据。
        "type": "retrieval", "sources": [], "candidate_count": count, "retrieved_count": count,
        "query_count": query_count, "query_rewritten": rewritten != question,
        "timings_ms": timings,
    }
    if not docs or not settings.is_llm_available:
        answer = _fallback_answer(candidate_sources)
        accepted_sources = filter_sources_by_citations(answer, candidate_sources)
        yield {"type": "content", "content": answer}
    else:
        generation_started = time.perf_counter()
        chain = ChatPromptTemplate.from_messages([
            ("system", RAG_SYSTEM_PROMPT), ("user", RAG_USER_PROMPT),
        ]) | get_llm(temperature=0.1)
        answer_parts: list[str] = []
        try:
            async for chunk in chain.astream({"question": rewritten, "context": _format_context(docs)}):
                content = str(getattr(chunk, "content", ""))
                if content:
                    answer_parts.append(content)
                    yield {"type": "content", "content": content}
            validated = _validate_citations("".join(answer_parts), candidate_sources)
            if validated != "".join(answer_parts).strip():
                # 先流式展示，再以合法引用版本原子替换最终答案。
                yield {"type": "replace_content", "content": validated}
            answer = validated
        except Exception:
            answer = _fallback_answer(candidate_sources)
            yield {"type": "content", "content": answer}
        timings["generation"] = round((time.perf_counter() - generation_started) * 1000, 1)
    timings["total"] = round((time.perf_counter() - started) * 1000, 1)
    yield {
        "type": "done", "sources": filter_sources_by_citations(answer, candidate_sources),
        "candidate_count": count, "timings_ms": timings,
    }
