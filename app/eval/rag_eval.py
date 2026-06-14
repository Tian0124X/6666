"""
RAG 评测引擎 — NDCG / Precision / Recall / Keyword Match

对标技术文档 1.5 成功指标:
- RAG 问答准确率 ≥ 85%
- 幻觉率 < 5%
"""

import time
import logging
from typing import List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RAGEvalResult:
    question_id: str
    question: str
    answer: str
    keywords_hit: int
    keywords_total: int
    keyword_recall: float   # 关键词召回率
    latency_ms: float
    passed: bool            # recall >= 0.5 即通过

@dataclass
class RAGEvalReport:
    results: List[RAGEvalResult] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    avg_recall: float = 0.0
    avg_latency_ms: float = 0.0
    accuracy: float = 0.0


def evaluate_keywords(answer: str, keywords: List[str]) -> tuple[int, int, float]:
    """基于关键词匹配的快速评测"""
    if not keywords:
        return 0, 0, 1.0
    answer_lower = answer.lower()
    hit = sum(1 for kw in keywords if kw.lower() in answer_lower)
    recall = hit / len(keywords)
    return hit, len(keywords), recall


async def run_rag_eval(limit: int = 0, verbose: bool = False) -> RAGEvalReport:
    """
    运行 RAG 评测。

    对内置测试集逐一执行 RAG 问答，评测关键词召回率。
    """
    from app.eval.testset import RAG_TESTSET
    from app.rag.retriever import rag_qa

    testset = RAG_TESTSET[:limit] if limit > 0 else RAG_TESTSET
    report = RAGEvalReport(total=len(testset))

    for item in testset:
        start = time.time()
        try:
            result = await rag_qa(question=item["question"], k=5, use_expansion=True, use_rerank=True)
            answer = result.get("answer", "")
        except Exception as e:
            answer = f"ERROR: {e}"

        latency = (time.time() - start) * 1000
        hit, total_kw, recall = evaluate_keywords(answer, item["keywords"])

        eval_result = RAGEvalResult(
            question_id=item["id"],
            question=item["question"],
            answer=answer[:300],
            keywords_hit=hit,
            keywords_total=total_kw,
            keyword_recall=round(recall, 3),
            latency_ms=round(latency, 1),
            passed=recall >= 0.5,
        )
        report.results.append(eval_result)

        if eval_result.passed:
            report.passed += 1

        if verbose:
            status = "✅" if eval_result.passed else "❌"
            logger.info(f"  {status} {item['id']}: recall={recall:.1%} ({latency:.0f}ms)")

    report.avg_recall = round(
        sum(r.keyword_recall for r in report.results) / max(len(report.results), 1), 3
    )
    report.avg_latency_ms = round(
        sum(r.latency_ms for r in report.results) / max(len(report.results), 1), 1
    )
    report.accuracy = round(report.passed / max(report.total, 1), 3)

    logger.info(
        f"RAG 评测完成: accuracy={report.accuracy:.1%} "
        f"({report.passed}/{report.total}) "
        f"avg_recall={report.avg_recall:.1%} "
        f"avg_latency={report.avg_latency_ms:.0f}ms"
    )
    return report
