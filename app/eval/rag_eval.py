"""
RAG 评测引擎 — 双模式: 快速关键词匹配 + RAGAS 标准评测

快速模式 (mode=fast):
  - 关键词子串匹配，秒级返回
  - 适合 CI/CD 快速检查

RAGAS 模式 (mode=ragas):
  - faithfulness, answer_relevancy, context_precision, context_recall
  - answer_correctness, context_entity_recall, noise_sensitivity (0.4+)
  - LLM 驱动评估，分钟级返回
  - 适合正式评测报告

2026 升级: RAGAS 0.4+ API (EvaluationDataset, metrics.collections)
运行要求: Python <3.14 (用 py -3.12 运行)
"""

import time
import asyncio
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
    # RAGAS 指标 (可选) — 0.4+ 新增 answer_correctness, context_entity_recall
    faithfulness: float | None = None
    answer_relevancy: float | None = None
    context_precision: float | None = None
    context_recall: float | None = None
    answer_correctness: float | None = None
    context_entity_recall: float | None = None
    # 延迟分阶段追踪 (ms)
    retrieval_latency_ms: float | None = None
    generation_latency_ms: float | None = None
    expansion_latency_ms: float | None = None
    # Token 与成本
    estimated_tokens: int = 0
    estimated_cost_cny: float = 0.0


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
    avg_answer_correctness: float | None = None
    avg_context_entity_recall: float | None = None


# ====== Token 成本估算 ======

# DeepSeek 定价 (2026, 单位: 元/1M tokens)
_DEEPSEEK_PRICE = {
    "deepseek-chat":    {"input": 1.0, "output": 2.0},
    "deepseek-reasoner": {"input": 4.0, "output": 16.0},
    "deepseek-v3":      {"input": 2.0, "output": 8.0},
}


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数 (中文 ~1.5 char/token, 英文 ~4 char/token)"""
    chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars / 1.5 + other_chars / 4)


def estimate_cost(
    prompt_text: str,
    response_text: str,
    model: str = "deepseek-chat",
) -> float:
    """估算单次 LLM 调用的成本 (人民币/元)"""
    pricing = _DEEPSEEK_PRICE.get(model, _DEEPSEEK_PRICE["deepseek-chat"])
    input_tokens = estimate_tokens(prompt_text)
    output_tokens = estimate_tokens(response_text)
    cost = (input_tokens / 1_000_000) * pricing["input"] + \
           (output_tokens / 1_000_000) * pricing["output"]
    return round(cost, 6)


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
        from ragas.metrics.collections import (
            Faithfulness,
            AnswerRelevancy,
            ContextPrecision,
            ContextRecall,
            AnswerCorrectness,
            ContextEntityRecall,
        )
        from ragas.dataset_schema import SingleTurnSample, EvaluationDataset
        from langchain_openai import ChatOpenAI
        from app.config import settings

        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=0,
            timeout=60,
        )

        # 构建 RAGAS 0.4+ 样本 (字段名已更新)
        sample = SingleTurnSample(
            user_input=question,
            response=answer,
            reference=ground_truth,
            retrieved_contexts=contexts or [],
        )

        # 包装为 EvaluationDataset (0.4+ 新 API)
        ds = EvaluationDataset(samples=[sample])

        metrics = [
            Faithfulness(),
            AnswerRelevancy(),
            ContextPrecision(),
            ContextRecall(),
            AnswerCorrectness(),
            ContextEntityRecall(),
        ]

        result = evaluate(
            dataset=ds,
            metrics=metrics,
            llm=llm,
        )

        # 提取分数
        df = result.to_pandas()
        scores = {}
        target_cols = [
            "faithfulness", "answer_relevancy", "context_precision",
            "context_recall", "answer_correctness", "context_entity_recall",
        ]
        for col in df.columns:
            col_lower = col.lower().replace(" ", "_")
            if col_lower in target_cols:
                val = df[col].iloc[0]
                scores[col_lower] = round(float(val), 3) if val is not None else 0.0

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
        retrieval_lat = None
        gen_lat = None

        try:
            # 分阶段计时：检索 + 生成
            # 先用内部函数分别测量（不改变 rag_qa 接口）
            from app.rag.retriever import _hybrid_search, _llm_rerank, _generate_answer, _expand_queries

            # 阶段1: 查询扩展
            exp_start = time.time()
            queries = _expand_queries(item["question"])
            exp_lat = (time.time() - exp_start) * 1000

            # 阶段2: 检索
            ret_start = time.time()
            fetch_k = 20
            all_results = await asyncio.gather(*[
                _hybrid_search(q, k=fetch_k) for q in queries
            ])
            from app.rag.retriever import _reciprocal_rank_fusion
            all_docs = _reciprocal_rank_fusion(list(all_results))
            final_docs = _llm_rerank(item["question"], all_docs, top_n=5)
            retrieval_lat = (time.time() - ret_start) * 1000

            # 阶段3: 生成
            gen_start = time.time()
            answer, _ = _generate_answer(item["question"], final_docs)
            gen_lat = (time.time() - gen_start) * 1000

            # 提取上下文
            sources = [{"excerpt": d.page_content[:200], "filename": d.metadata.get("filename", "")}
                       for d in final_docs]
            contexts = [s.get("excerpt", "") for s in sources]
        except Exception as e:
            answer = f"ERROR: {e}"

        latency = (time.time() - start) * 1000

        # 估算 token 和成本
        context_text = "\n".join(contexts)
        prompt_text = context_text + "\n" + item["question"]
        est_tokens = estimate_tokens(prompt_text) + estimate_tokens(answer)
        est_cost = estimate_cost(prompt_text, answer)

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
            # 分阶段延迟
            retrieval_latency_ms=round(retrieval_lat, 1) if retrieval_lat else None,
            generation_latency_ms=round(gen_lat, 1) if gen_lat else None,
            expansion_latency_ms=round(exp_lat, 1) if exp_lat else None,
            # 成本估算
            estimated_tokens=est_tokens,
            estimated_cost_cny=est_cost,
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
                eval_result.answer_correctness = ragas_scores.get("answer_correctness")
                eval_result.context_entity_recall = ragas_scores.get("context_entity_recall")
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
                extra = (f" faith={eval_result.faithfulness:.2f} rel={eval_result.answer_relevancy:.2f}"
                         f" correct={eval_result.answer_correctness:.2f}" if eval_result.answer_correctness else "")
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
        report.avg_answer_correctness = round(sum(s.get("answer_correctness", 0) or 0 for s in ragas_scores_list) / n, 3)
        report.avg_context_entity_recall = round(sum(s.get("context_entity_recall", 0) or 0 for s in ragas_scores_list) / n, 3)

    # 统计总 tokens 和成本
    total_tokens = sum(r.estimated_tokens for r in report.results)
    total_cost = sum(r.estimated_cost_cny for r in report.results)
    avg_ret_lat = sum(r.retrieval_latency_ms or 0 for r in report.results) / max(len(report.results), 1)
    avg_gen_lat = sum(r.generation_latency_ms or 0 for r in report.results) / max(len(report.results), 1)

    metric_name = "faithfulness" if report.mode == "ragas" else "keyword_recall"
    logger.info(
        f"RAG 评测完成 [{report.mode}]: accuracy={report.accuracy:.1%} "
        f"({report.passed}/{report.total}) "
        f"avg_{metric_name}={report.avg_faithfulness or report.avg_recall:.1%} "
        f"avg_latency={report.avg_latency_ms:.0f}ms "
        f"(检索{avg_ret_lat:.0f}ms + 生成{avg_gen_lat:.0f}ms) "
        f"tokens={total_tokens} cost=¥{total_cost:.4f}"
    )
    return report
