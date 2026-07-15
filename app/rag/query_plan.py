"""将用户问题转换为可控的检索计划，不让模型改写显式过滤条件。"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from app.config import settings
from app.rag.llm_factory import get_llm


FOLLOW_UP_MARKERS = ("这个", "那个", "它", "上面", "刚才", "前面", "继续", "分别", "其中")
_FILENAME_PATTERN = re.compile(r"(?<![\w-])([^\s，。；、,;：:《》]+\.(?:pdf|docx|xlsx|xls|txt|csv))", re.IGNORECASE)
_PAGE_PATTERN = re.compile(r"第?\s*(\d+)\s*(?:页\s*(?:到|至|[-~])\s*第?\s*(\d+)\s*页?|(?:到|至|[-~])\s*第?\s*(\d+)\s*页)")
_SINGLE_PAGE_PATTERN = re.compile(r"第\s*(\d+)\s*页")
_SHEET_PATTERN = re.compile(r"(?:sheet|工作表)\s*(?:为|是|[:：])?\s*[\"“”']?([\w\-\u4e00-\u9fff]+)", re.IGNORECASE)
_FILE_TYPE_PATTERN = re.compile(r"(?<![\w.])(pdf|docx|xlsx|xls|txt|csv)(?:\s*(?:文件|文档|格式))?", re.IGNORECASE)


@dataclass(frozen=True)
class QueryFilters:
    """仅保存用户在问题中明确表达、可安全下推到数据库的条件。"""

    filenames: tuple[str, ...] = ()
    page_start: int | None = None
    page_end: int | None = None
    sheet: str | None = None
    file_types: tuple[str, ...] = ()

    def to_store_filters(self) -> dict[str, Any]:
        """转换为存储层参数，空条件不会参与 SQL 拼接。"""
        result: dict[str, Any] = {}
        if self.filenames:
            result["filenames"] = list(self.filenames)
        if self.page_start is not None:
            result["page_start"] = self.page_start
            result["page_end"] = self.page_end or self.page_start
        if self.sheet:
            result["sheet"] = self.sheet
        if self.file_types:
            result["file_types"] = list(self.file_types)
        return result

    def to_trace(self) -> dict[str, Any]:
        """返回不含问题正文的结构化追踪摘要。"""
        return self.to_store_filters()


@dataclass
class QueryPlan:
    """一次检索允许使用的标准问题、变体与显式过滤条件。"""

    original_query: str
    canonical_query: str
    variants: list[str] = field(default_factory=list)
    filters: QueryFilters = field(default_factory=QueryFilters)
    source: str = "rules"
    fallback_reason: str | None = None
    planning_ms: float = 0.0

    @property
    def queries(self) -> list[str]:
        """保持主问题优先，去重后最多保留配置允许的检索变体。"""
        queries: list[str] = []
        for query in [self.canonical_query, *self.variants[:max(0, settings.RAG_QUERY_PLAN_VARIANT_LIMIT)]]:
            normalized = query.strip()
            if normalized and normalized not in queries:
                queries.append(normalized)
        return queries or [self.original_query]

    def trace_summary(self) -> dict[str, Any]:
        """供内部日志使用，避免记录对话和检索正文。"""
        return {
            "source": self.source,
            "filters": self.filters.to_trace(),
            "query_count": len(self.queries),
            "fallback_reason": self.fallback_reason,
            "planning_ms": self.planning_ms,
        }


def is_follow_up(question: str) -> bool:
    """只对短且含指代的句子视为需要上下文的追问。"""
    normalized = question.strip()
    return len(normalized) <= 36 and any(marker in normalized for marker in FOLLOW_UP_MARKERS)


def extract_explicit_filters(question: str) -> QueryFilters:
    """解析文件、页码和 Sheet 等明确条件；不从模型输出中补造条件。"""
    # 中文方括号可能是文件名的一部分，只移除作为引用符号的书名号。
    filenames = tuple(dict.fromkeys(match.group(1).strip("《》") for match in _FILENAME_PATTERN.finditer(question)))
    range_match = _PAGE_PATTERN.search(question)
    page_start = page_end = None
    if range_match:
        page_start = int(range_match.group(1))
        page_end = int(range_match.group(2) or range_match.group(3) or page_start)
        page_start, page_end = min(page_start, page_end), max(page_start, page_end)
    else:
        single_page = _SINGLE_PAGE_PATTERN.search(question)
        if single_page:
            page_start = page_end = int(single_page.group(1))
    sheet_match = _SHEET_PATTERN.search(question)
    file_types = tuple(dict.fromkeys(match.group(1).lower() for match in _FILE_TYPE_PATTERN.finditer(question)))
    return QueryFilters(
        filenames=filenames,
        page_start=page_start,
        page_end=page_end,
        sheet=sheet_match.group(1) if sheet_match else None,
        file_types=file_types,
    )


def build_rule_plan(question: str) -> QueryPlan:
    """普通问题的零模型调用计划。"""
    return QueryPlan(
        original_query=question,
        canonical_query=question,
        filters=extract_explicit_filters(question),
    )


async def build_llm_plan(question: str, history: list[dict] | None, base_plan: QueryPlan) -> QueryPlan:
    """仅在已判定需要时生成检索变体，失败时保守回退规则计划。"""
    started = time.perf_counter()
    if not settings.is_llm_available:
        base_plan.source = "fallback"
        base_plan.fallback_reason = "llm_unavailable"
        return base_plan
    memory_notes = [item for item in (history or []) if item.get("role") == "system"][:2]
    recent_turns = [item for item in (history or []) if item.get("role") in {"user", "assistant"}][-4:]
    history_text = "\n".join(
        f"{item.get('role', 'user')}: {str(item.get('content', ''))[:500]}"
        for item in memory_notes + recent_turns
    )
    prompt = ChatPromptTemplate.from_template(
        """将问题转换为独立、适合知识库检索的表述，并给出最多两条同义检索变体。
只能输出 JSON 对象：{{\"canonical_query\": \"...\", \"variants\": [\"...\"]}}。
不要添加文件、页码、时间或 Sheet 条件；无法判断时 canonical_query 必须保留原问题且 variants 为空。

对话历史：
{history}

问题：{question}"""
    )
    try:
        response = await asyncio.wait_for(
            (prompt | get_llm(temperature=0, timeout=2, max_tokens=180)).ainvoke(
                {"history": history_text, "question": question}
            ),
            timeout=2.5,
        )
        payload = json.loads(str(response.content).strip())
        canonical = payload.get("canonical_query")
        variants = payload.get("variants", [])
        if not isinstance(canonical, str) or not canonical.strip() or not isinstance(variants, list):
            raise ValueError("模型输出不符合 QueryPlan 结构")
        clean_variants = [
            item.strip() for item in variants
            if isinstance(item, str) and item.strip() and len(item.strip()) <= 400
        ][:max(0, settings.RAG_QUERY_PLAN_VARIANT_LIMIT)]
        return QueryPlan(
            original_query=question,
            canonical_query=canonical.strip()[:400],
            variants=clean_variants,
            filters=base_plan.filters,
            source="llm",
            planning_ms=round((time.perf_counter() - started) * 1000, 1),
        )
    except Exception as exc:
        base_plan.source = "fallback"
        base_plan.fallback_reason = type(exc).__name__
        base_plan.planning_ms = round((time.perf_counter() - started) * 1000, 1)
        return base_plan
