"""纯 RAG 问答链路：改写、单次召回、引用生成与过程追踪。"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Iterable

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

from app.config import settings
from app.rag.llm_factory import get_llm
from app.rag.store import get_vector_search_results

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
FOLLOW_UP_MARKERS = ("这个", "那个", "它", "上面", "刚才", "前面", "继续", "分别", "其中")


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


def _is_follow_up(question: str) -> bool:
    return len(question.strip()) <= 36 and any(marker in question for marker in FOLLOW_UP_MARKERS)


async def _rewrite_follow_up(question: str, history: list[dict] | None) -> tuple[str, float, bool]:
    """仅将明显追问改写为独立检索问题，普通问题不增加 LLM 往返。"""
    started = time.perf_counter()
    if not history or not _is_follow_up(question) or not settings.is_llm_available:
        return question, 0.0, False
    context = "\n".join(
        f"{item.get('role', 'user')}: {str(item.get('content', ''))[:500]}"
        for item in history[-4:]
    )
    prompt = ChatPromptTemplate.from_template(
        """根据对话历史把最后一个追问改写为可独立检索的一句话。
只输出改写后的问题，无法判断时原样输出。

历史：
{history}

追问：{question}"""
    )
    try:
        answer = await asyncio.wait_for(
            (prompt | get_llm(temperature=0, timeout=2, max_tokens=120)).ainvoke(
                {"history": context, "question": question}
            ),
            timeout=2.5,
        )
        rewritten = str(answer.content).strip() or question
        return rewritten, round((time.perf_counter() - started) * 1000, 1), rewritten != question
    except Exception:
        return question, round((time.perf_counter() - started) * 1000, 1), False


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


async def _hybrid_search(query: str, k: int = 20) -> list[Document]:
    """兼容评测接口；内部只执行 pgvector 的单次融合检索。"""
    return await asyncio.to_thread(get_vector_search_results, query, k, max(30, k))


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
    started = time.perf_counter()
    docs = await _hybrid_search(question, k=max(k, settings.RAG_SEARCH_K))
    timings = {
        "expansion": 0.0,
        "retrieval": round((time.perf_counter() - started) * 1000, 1),
        "rerank": 0.0,
    }
    if use_rerank and settings.RAG_ONLINE_RERANK:
        rerank_started = time.perf_counter()
        docs = await asyncio.to_thread(_cross_encoder_rerank, question, docs, k)
        timings["rerank"] = round((time.perf_counter() - rerank_started) * 1000, 1)
    else:
        docs = docs[:k]
    timings["total_retrieval"] = round((time.perf_counter() - started) * 1000, 1)
    return docs, len(docs), timings, 1


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
    rewritten, rewrite_ms, rewritten_flag = await _rewrite_follow_up(question, history)
    docs, count, timings, query_count = await _retrieve_final_documents(
        rewritten, k, use_expansion=False, use_rerank=False
    )
    timings["query_rewrite"] = rewrite_ms
    timings["total_retrieval"] = round((time.perf_counter() - started) * 1000, 1)
    candidate_sources = build_sources(docs)
    yield {
        # 候选仅用于展示过程数量，避免把未采纳文档误导为回答依据。
        "type": "retrieval", "sources": [], "candidate_count": count, "retrieved_count": count,
        "query_count": query_count, "query_rewritten": rewritten_flag,
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
