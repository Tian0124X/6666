"""将用户问题转换为可控的检索计划，不让模型改写显式过滤条件。"""

from __future__ import annotations

import asyncio
import json
import re
import time
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date
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
_EXACT_IDENTIFIER_PATTERN = re.compile(r"\b[A-Za-z]{1,12}[-_]?\d{2,}\b")
_DATE_TOKEN_PATTERN = re.compile(
    r"(?<!\d)(?P<year>(?:19|20)\d{2})(?:\s*年\s*(?P<cn_month>0?[1-9]|1[0-2])\s*月(?:\s*(?P<cn_day>0?[1-9]|[12]\d|3[01])\s*日?)?|[-/.](?P<num_month>0?[1-9]|1[0-2])(?:[-/.](?P<num_day>0?[1-9]|[12]\d|3[01]))?)(?!\d)"
)
_YEAR_PATTERN = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*年(?!\s*\d)")
_DATE_RANGE_CONNECTOR_PATTERN = re.compile(r"\s*(?:到|至|[-~—–])\s*$")


@dataclass(frozen=True)
class QueryFilters:
    """仅保存用户在问题中明确表达、可安全下推到数据库的条件。"""

    filenames: tuple[str, ...] = ()
    page_start: int | None = None
    page_end: int | None = None
    sheet: str | None = None
    file_types: tuple[str, ...] = ()
    document_date_start: str | None = None
    document_date_end: str | None = None

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
        if self.document_date_start:
            result["document_date_start"] = self.document_date_start
        if self.document_date_end:
            result["document_date_end"] = self.document_date_end
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
    trace_id: str = ""

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


def _date_token_range(match: re.Match[str]) -> tuple[str, str] | None:
    """将年月日或年月解析为可比较的 ISO 日期区间。"""
    year = int(match.group("year"))
    month = int(match.group("cn_month") or match.group("num_month"))
    day_text = match.group("cn_day") or match.group("num_day")
    try:
        if day_text:
            exact = date(year, month, int(day_text)).isoformat()
            return exact, exact
        return date(year, month, 1).isoformat(), date(year, month, monthrange(year, month)[1]).isoformat()
    except ValueError:
        return None


def _extract_document_date_range(question: str) -> tuple[str | None, str | None]:
    """只解析用户明确给出的日期，不从文件名、文件时间或模型结果推断。"""
    tokens = [
        (match.start(), match.end(), value)
        for match in _DATE_TOKEN_PATTERN.finditer(question)
        if (value := _date_token_range(match)) is not None
    ]
    if len(tokens) >= 2:
        _, first_end, first_range = tokens[0]
        second_start, _, second_range = tokens[1]
        if _DATE_RANGE_CONNECTOR_PATTERN.fullmatch(question[first_end:second_start]):
            return first_range[0], second_range[1]
    if tokens:
        return tokens[0][2]

    year_match = _YEAR_PATTERN.search(question)
    if not year_match:
        return None, None
    year = int(year_match.group(1))
    suffix = question[year_match.end():year_match.end() + 4]
    if re.match(r"\s*(?:之后|以后|起|以来)", suffix):
        return date(year, 1, 1).isoformat(), None
    if re.match(r"\s*(?:之前|以前|截止|截至)", suffix):
        return None, date(year, 12, 31).isoformat()
    return date(year, 1, 1).isoformat(), date(year, 12, 31).isoformat()


def extract_explicit_filters(question: str) -> QueryFilters:
    """解析文件、页码、Sheet 和日期等明确条件；不从模型输出中补造条件。"""
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
    document_date_start, document_date_end = _extract_document_date_range(question)
    return QueryFilters(
        filenames=filenames,
        page_start=page_start,
        page_end=page_end,
        sheet=sheet_match.group(1) if sheet_match else None,
        file_types=file_types,
        document_date_start=document_date_start,
        document_date_end=document_date_end,
    )


def extract_exact_identifiers(question: str) -> tuple[str, ...]:
    """提取不可被 Query 改写改变的业务主键、订单号等精确标识符。"""
    return tuple(dict.fromkeys(match.upper() for match in _EXACT_IDENTIFIER_PATTERN.findall(question)))


def build_rule_plan(question: str) -> QueryPlan:
    """普通问题的零模型调用计划。"""
    return QueryPlan(
        original_query=question,
        canonical_query=question,
        variants=_build_rule_variants(question),
        filters=extract_explicit_filters(question),
    )


def _build_rule_variants(question: str) -> list[str]:
    """只对高价值领域同义表达生成确定性变体，不调用模型也不改动显式条件。"""
    variants: list[str] = []
    normalized = question.replace(" ", "")
    if "年假" in normalized and "年休假" not in normalized:
        variants.append(question.replace("年假", "年休假"))
    if "新员工" in normalized and "累计工龄" in normalized:
        variants.append("新入职员工累计工龄佐证材料提交期限")
    if "同一部门" in normalized and "休假" in normalized and ("上限" in normalized or "比例" in normalized):
        variants.append("同一部门同时间段休假人数不得超过部门在岗人数")
    return variants[:max(0, settings.RAG_QUERY_PLAN_VARIANT_LIMIT)]


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
不要添加文件、页码、时间或 Sheet 条件；不得删除、替换或编造问题中的业务标识符（如 SP0001）；无法判断时 canonical_query 必须保留原问题且 variants 为空。

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
        required_identifiers = extract_exact_identifiers(question)
        candidate_queries = [canonical.strip(), *clean_variants]
        if required_identifiers and any(
            any(identifier not in candidate.upper() for identifier in required_identifiers)
            for candidate in candidate_queries
        ):
            raise ValueError("模型改写丢失业务标识符")
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
