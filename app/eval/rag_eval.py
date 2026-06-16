"""
RAG 评测引擎 — 双模式: 快速关键词匹配 + RAGAS 标准评测

快速模式 (mode=fast):
  - 关键词子串匹配，秒级返回
  - 适合 CI/CD 快速检查

RAGAS 模式 (mode=ragas):
  - faithfulness, answer_relevancy, context_precision, context_recall
  - LLM 驱动评估，分钟级返回
  - 适合正式评测报告

2026 升级: RAGAS 0.3+ 双模式架构
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
    keyword_recall: float
    latency_ms: float
    passed: bool
    # RAGAS 指标 (可选)
    faithfulness: float | None = None
    answer_relevancy: float | None = None
    context_precision: float | None = None
    context_recall: float | None = None


@dataclass
class RAGEvalReport:
    results: List[RAGEvalResult] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    avg_recall: float = 0.0
    avg_latency_ms: float = 0.0
    accuracy: float = 0.0
    mode: str = "fast"
    # RAGAS 汇总
    avg_faithfulness: float | None = None
    avg_answer_relevancy: float | None = None
    avg_context_precision: float | None = None
    avg_context_recall: float | None = None


# ====== 快速模式: 关键词匹配 ======

def evaluate_keywords(answer: str, keywords: List[str]) -> tuple[int, int, float]:
    """
    基于关键词匹配的快速评测。

    短关键词(<2字符) 使用空白分词精确匹配避免假阳性。
    例如 "天" 不会匹配 "今天" 中的 "天"。
    """
    if not keywords:
        return 0, 0, 1.0
    answer_lower = answer.lower()
    hit = 0
    for kw in keywords:
        kw_lower = kw.lower()
        if len(kw) < 2:
            if kw_lower in answer_lower.split():
                hit += 1
        else:
            if kw_lower in answer_lower:
                hit += 1
    recall = hit / len(keywords)
    return hit, len(keywords), recall


# ====== RAGAS 模式: 标准 LLM 评测 ======

async def _run_ragas_single(
    question: str,
    answer: str,
    ground_truth: str,
    contexts: List[str],
) -> dict:
    """
    用 RAGAS 对单个样本进行评测。

    Returns:
        {"faithfulness": float, "answer_relevancy": float,
         "context_precision": float, "context_recall": float}
    """
    try:
        from ragas import evaluate
        from ragas.metrics import (
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        )
        from ragas.dataset_schema import SingleTurnSample
        from langchain_openai import ChatOpenAI
        from app.config import settings

        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=0,
            timeout=60,
        )

        # 构建 RAGAS 样本
        sample = SingleTurnSample(
            user_input=question,
            response=answer,
            reference=ground_truth,
            retrieved_contexts=contexts or [],
        )

        metrics = [faithfulness, answer_relevancy, context_precision, context_recall]

        result = evaluate(
            dataset=[sample],
            metrics=metrics,
            llm=llm,
        )

        # 提取分数
        df = result.to_pandas()
        scores = {}
        for col in df.columns:
            if col in ("faithfulness", "answer_relevancy", "context_precision", "context_recall"):
                val = df[col].iloc[0]
                scores[col] = round(float(val), 3) if val is not None else 0.0

        return scores

    except ImportError:
        logger.warning("ragas 未安装，降级为关键词模式")
        return {}
    except Exception as e:
        logger.warning(f"RAGAS 评测失败 (Q: {question[:30]}...): {e}")
        return {}


async def run_rag_eval(
    limit: int = 0,
    verbose: bool = False,
    mode: str = "fast",
) -> RAGEvalReport:
    """
    运行 RAG 评测。

    Args:
        limit: 限制测试用例数量 (0 = 全部)
        verbose: 输出详细日志
        mode: "fast" (关键词) | "ragas" (LLM评测)
    """
    from app.eval.testset import RAG_TESTSET
    from app.rag.retriever import rag_qa

    testset = RAG_TESTSET[:limit] if limit > 0 else RAG_TESTSET
    report = RAGEvalReport(total=len(testset), mode=mode)

    ragas_scores_list = []

    for item in testset:
        start = time.time()
        answer = ""
        contexts = []

        try:
            result = await rag_qa(
                question=item["question"],
                k=5,
                use_expansion=True,
                use_rerank=True,
            )
            answer = result.get("answer", "")
            # 提取上下文
            sources = result.get("sources", [])
            contexts = [s.get("excerpt", s.get("filename", "")) for s in sources]
        except Exception as e:
            answer = f"ERROR: {e}"

        latency = (time.time() - start) * 1000

        # 关键词匹配 (始终执行，作为基线)
        hit, total_kw, recall = evaluate_keywords(answer, item["keywords"])

        eval_result = RAGEvalResult(
            question_id=item["id"],
            question=item["question"],
            answer=answer[:500],
            keywords_hit=hit,
            keywords_total=total_kw,
            keyword_recall=round(recall, 3),
            latency_ms=round(latency, 1),
            passed=recall >= 0.5,
        )

        # RAGAS 评测（仅在 ragas 模式下执行）
        if mode == "ragas" and item.get("ground_truth"):
            ragas_scores = await _run_ragas_single(
                question=item["question"],
                answer=answer,
                ground_truth=item["ground_truth"],
                contexts=contexts,
            )
            if ragas_scores:
                eval_result.faithfulness = ragas_scores.get("faithfulness")
                eval_result.answer_relevancy = ragas_scores.get("answer_relevancy")
                eval_result.context_precision = ragas_scores.get("context_precision")
                eval_result.context_recall = ragas_scores.get("context_recall")
                # RAGAS 模式下: faithfulness >= 0.7 视为通过
                eval_result.passed = (ragas_scores.get("faithfulness", 0) or 0) >= 0.7
                ragas_scores_list.append(ragas_scores)

        report.results.append(eval_result)

        if eval_result.passed:
            report.passed += 1

        if verbose:
            status = "✅" if eval_result.passed else "❌"
            extra = ""
            if eval_result.faithfulness is not None:
                extra = f" faith={eval_result.faithfulness:.2f} rel={eval_result.answer_relevancy:.2f}"
            logger.info(f"  {status} {item['id']}: recall={recall:.1%} ({latency:.0f}ms){extra}")

    # 汇总
    report.avg_recall = round(
        sum(r.keyword_recall for r in report.results) / max(len(report.results), 1), 3
    )
    report.avg_latency_ms = round(
        sum(r.latency_ms for r in report.results) / max(len(report.results), 1), 1
    )
    report.accuracy = round(report.passed / max(report.total, 1), 3)

    # RAGAS 汇总
    if ragas_scores_list:
        n = len(ragas_scores_list)
        report.avg_faithfulness = round(sum(s.get("faithfulness", 0) or 0 for s in ragas_scores_list) / n, 3)
        report.avg_answer_relevancy = round(sum(s.get("answer_relevancy", 0) or 0 for s in ragas_scores_list) / n, 3)
        report.avg_context_precision = round(sum(s.get("context_precision", 0) or 0 for s in ragas_scores_list) / n, 3)
        report.avg_context_recall = round(sum(s.get("context_recall", 0) or 0 for s in ragas_scores_list) / n, 3)

    metric_name = "faithfulness" if report.mode == "ragas" else "keyword_recall"
    logger.info(
        f"RAG 评测完成 [{report.mode}]: accuracy={report.accuracy:.1%} "
        f"({report.passed}/{report.total}) "
        f"avg_{metric_name}={report.avg_faithfulness or report.avg_recall:.1%} "
        f"avg_latency={report.avg_latency_ms:.0f}ms"
    )
    return report
