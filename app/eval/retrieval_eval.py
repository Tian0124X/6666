"""
检索质量专项测评 — 纯检索环节指标，不依赖 LLM

指标:
  - Recall@K: Top-K 中相关文档占全部相关文档的比例
  - Precision@K: Top-K 中相关文档的比例
  - MRR: 第一个相关文档排名的倒数均值
  - NDCG@K: 归一化折损累计增益（支持相关性分级 0-3）
  - Hit Rate: Top-K 中至少命中一条相关文档的查询比例

支持检索策略对比:
  - vector_only: 纯语义检索
  - hybrid: 向量 + BM25 + RRF 融合
  - hybrid_rerank: 混合 + BGE Cross-Encoder 重排序

用法:
  python -m app.eval.retrieval_eval              # 运行全部对比
  python -m app.eval.retrieval_eval --strategy hybrid_rerank  # 单策略
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import List, Dict, Optional, Literal
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

StrategyName = Literal["vector_only", "hybrid", "hybrid_rerank"]


# ============================================================
# 评估指标计算（纯数学，无 LLM）
# ============================================================

def _doc_matches_relevant(doc_source: str, relevant_sources: List[str]) -> bool:
    """检查文档来源是否匹配任一相关来源（文件名模糊匹配）"""
    import os
    doc_name = os.path.basename(doc_source).lower()
    for rel in relevant_sources:
        rel_name = os.path.basename(rel).lower()
        if rel_name in doc_name or doc_name in rel_name:
            return True
    return False


def _binary_relevance(
    retrieved_sources: List[str],
    relevant_sources: List[str],
) -> List[int]:
    """二值相关性: 1=相关, 0=不相关"""
    return [1 if _doc_matches_relevant(s, relevant_sources) else 0
            for s in retrieved_sources]


def recall_at_k(
    retrieved_sources: List[str],
    relevant_sources: List[str],
    k: int = 5,
) -> float:
    """Recall@K: Top-K 结果中命中相关文档数 / 相关文档总数"""
    if not relevant_sources:
        return 1.0
    top_k = retrieved_sources[:k]
    hits = sum(1 for s in top_k if _doc_matches_relevant(s, relevant_sources))
    return hits / len(relevant_sources)


def precision_at_k(
    retrieved_sources: List[str],
    relevant_sources: List[str],
    k: int = 5,
) -> float:
    """Precision@K: Top-K 中相关文档数 / K"""
    if k <= 0:
        return 0.0
    top_k = retrieved_sources[:k]
    hits = sum(1 for s in top_k if _doc_matches_relevant(s, relevant_sources))
    return hits / k


def mrr(
    queries_retrieved: List[List[str]],  # 每个查询的检索结果列表
    queries_relevant: List[List[str]],   # 每个查询的相关文档列表
) -> float:
    """MRR (Mean Reciprocal Rank): 第一个相关文档排名倒数的均值"""
    if not queries_retrieved:
        return 0.0
    reciprocal_ranks = []
    for retrieved, relevant in zip(queries_retrieved, queries_relevant):
        for rank, source in enumerate(retrieved, 1):
            if _doc_matches_relevant(source, relevant):
                reciprocal_ranks.append(1.0 / rank)
                break
        else:
            reciprocal_ranks.append(0.0)
    return sum(reciprocal_ranks) / len(reciprocal_ranks)


def ndcg_at_k(
    retrieved_sources: List[str],
    relevance_map: Dict[str, int],  # source → 0-3 相关性分级
    k: int = 5,
) -> float:
    """
    NDCG@K: 归一化折损累计增益。

    relevance_map: {source_filename: relevance_grade}
      0 = 不相关, 1 = 弱相关, 2 = 相关, 3 = 高度相关

    DCG@K = Σ(2^rel_i - 1) / log2(i+1)
    NDCG@K = DCG@K / IDCG@K
    """
    if k <= 0 or not relevance_map:
        return 0.0

    import os

    def _get_rel(source: str) -> int:
        name = os.path.basename(source).lower()
        for rel_src, grade in relevance_map.items():
            if os.path.basename(rel_src).lower() in name or name in os.path.basename(rel_src).lower():
                return grade
        return 0

    # DCG
    dcg = 0.0
    for i, source in enumerate(retrieved_sources[:k], 1):
        rel = _get_rel(source)
        if rel > 0:
            dcg += (2 ** rel - 1) / math.log2(i + 1)

    # IDCG (理想排序: 所有相关文档按等级降序排在前面)
    ideal_rels = sorted(relevance_map.values(), reverse=True)[:k]
    idcg = 0.0
    for i, rel in enumerate(ideal_rels, 1):
        if rel > 0:
            idcg += (2 ** rel - 1) / math.log2(i + 1)

    return dcg / idcg if idcg > 0 else 0.0


def hit_rate(
    queries_retrieved: List[List[str]],
    queries_relevant: List[List[str]],
    k: int = 5,
) -> float:
    """Hit Rate@K: 至少命中一条相关文档的查询占比"""
    if not queries_retrieved:
        return 0.0
    hits = 0
    for retrieved, relevant in zip(queries_retrieved, queries_relevant):
        top_k = retrieved[:k]
        if any(_doc_matches_relevant(s, relevant) for s in top_k):
            hits += 1
    return hits / len(queries_retrieved)


# ============================================================
# 检索策略执行
# ============================================================

async def _retrieve_vector_only(query: str, k: int = 20) -> List:
    """纯向量检索（后端感知）"""
    from app.rag.store import get_vector_search_results
    return await asyncio.to_thread(get_vector_search_results, query, k, k * 3)


async def _retrieve_hybrid(query: str, k: int = 20) -> List:
    """混合检索: 向量 + BM25 + RRF"""
    from app.rag.retriever import _hybrid_search
    return await _hybrid_search(query, k=k)


async def _retrieve_hybrid_rerank(query: str, k: int = 20, top_n: int = 5) -> List:
    """混合检索 + BGE Cross-Encoder 重排序"""
    from app.rag.retriever import _hybrid_search, _cross_encoder_rerank
    docs = await _hybrid_search(query, k=k)
    if len(docs) > top_n:
        docs = await asyncio.to_thread(_cross_encoder_rerank, query, docs, top_n)
    return docs


STRATEGIES: Dict[StrategyName, dict] = {
    "vector_only": {
        "name": "纯向量检索",
        "func": _retrieve_vector_only,
    },
    "hybrid": {
        "name": "混合检索 (向量+BM25+RRF)",
        "func": _retrieve_hybrid,
    },
    "hybrid_rerank": {
        "name": "混合检索 + BGE Reranker",
        "func": _retrieve_hybrid_rerank,
    },
}


# ============================================================
# 数据结构
# ============================================================

@dataclass
class RetrievalEvalResult:
    """单次检索测评结果"""
    strategy: str
    recall_5: float = 0.0
    recall_10: float = 0.0
    recall_20: float = 0.0
    precision_5: float = 0.0
    precision_10: float = 0.0
    mrr: float = 0.0
    ndcg_5: float = 0.0
    ndcg_10: float = 0.0
    hit_rate_5: float = 0.0
    hit_rate_10: float = 0.0
    avg_latency_ms: float = 0.0
    total_queries: int = 0


@dataclass
class RetrievalCompareReport:
    """多策略对比报告"""
    results: List[RetrievalEvalResult] = field(default_factory=list)
    queries_count: int = 0


# ============================================================
# 主入口
# ============================================================

async def run_retrieval_eval(
    strategy: StrategyName = "hybrid_rerank",
    k_values: List[int] = None,
    verbose: bool = True,
) -> RetrievalEvalResult:
    """
    运行检索质量测评。

    Args:
        strategy: 检索策略
        k_values: 评估的 K 值列表，默认 [5, 10, 20]
        verbose: 输出详细日志

    Returns:
        RetrievalEvalResult
    """
    from app.eval.testset import RAG_TESTSET

    if k_values is None:
        k_values = [5, 10, 20]

    # 筛选有 relevant_docs 标注的测试用例
    testset = [t for t in RAG_TESTSET if t.get("relevant_docs")]
    if not testset:
        logger.warning("测试集中没有 relevant_docs 标注，跳过检索测评")
        return RetrievalEvalResult(strategy=strategy)

    strategy_info = STRATEGIES[strategy]
    retrieve_fn = strategy_info["func"]

    all_retrieved = []
    all_relevant = []
    all_relevance_maps = []
    latencies = []

    for item in testset:
        question = item["question"]
        relevant_docs = item.get("relevant_docs", [])
        relevance_grades = item.get("relevance_grades", {})  # {doc: 0-3}

        start = time.time()
        try:
            docs = await retrieve_fn(question, k=max(k_values))
        except Exception as e:
            logger.warning(f"检索失败 [{item['id']}]: {e}")
            docs = []
        latency = (time.time() - start) * 1000
        latencies.append(latency)

        # 提取文档来源
        sources = [d.metadata.get("source", d.metadata.get("filename", "")) for d in docs]

        all_retrieved.append(sources)
        all_relevant.append(relevant_docs)
        all_relevance_maps.append(relevance_grades)

        if verbose:
            hits_5 = sum(1 for s in sources[:5] if _doc_matches_relevant(s, relevant_docs))
            logger.info(f"  {item['id']}: {hits_5}/{len(relevant_docs)} hits@5 "
                         f"({latency:.0f}ms) [{strategy}]")

    # 计算指标
    result = RetrievalEvalResult(
        strategy=strategy,
        total_queries=len(testset),
        avg_latency_ms=round(sum(latencies) / max(len(latencies), 1), 1),
    )

    for k in k_values:
        recalls = [recall_at_k(r, rel, k) for r, rel in zip(all_retrieved, all_relevant)]
        precisions = [precision_at_k(r, rel, k) for r, rel in zip(all_retrieved, all_relevant)]

        avg_recall = sum(recalls) / max(len(recalls), 1)
        avg_precision = sum(precisions) / max(len(precisions), 1)

        setattr(result, f"recall_{k}", round(avg_recall, 3))
        setattr(result, f"precision_{k}", round(avg_precision, 3))

    result.mrr = round(mrr(all_retrieved, all_relevant), 3)

    # NDCG (仅对提供了 relevance_grades 的查询)
    ndcg_5_vals, ndcg_10_vals = [], []
    for retrieved, rel_map in zip(all_retrieved, all_relevance_maps):
        if rel_map:
            ndcg_5_vals.append(ndcg_at_k(retrieved, rel_map, 5))
            ndcg_10_vals.append(ndcg_at_k(retrieved, rel_map, 10))
    if ndcg_5_vals:
        result.ndcg_5 = round(sum(ndcg_5_vals) / len(ndcg_5_vals), 3)
        result.ndcg_10 = round(sum(ndcg_10_vals) / len(ndcg_10_vals), 3)

    result.hit_rate_5 = round(hit_rate(all_retrieved, all_relevant, 5), 3)
    result.hit_rate_10 = round(hit_rate(all_retrieved, all_relevant, 10), 3)

    if verbose:
        logger.info(
            f"\n{'='*60}\n"
            f"检索测评 [{strategy_info['name']}] (n={result.total_queries})\n"
            f"  Recall@5:    {result.recall_5:.1%}  | Recall@10: {result.recall_10:.1%}  | Recall@20: {result.recall_20:.1%}\n"
            f"  Precision@5: {result.precision_5:.1%}  | Precision@10: {result.precision_10:.1%}\n"
            f"  MRR:         {result.mrr:.3f}\n"
            f"  NDCG@5:      {result.ndcg_5:.3f}  | NDCG@10:   {result.ndcg_10:.3f}\n"
            f"  Hit Rate@5:  {result.hit_rate_5:.1%}  | Hit Rate@10: {result.hit_rate_10:.1%}\n"
            f"  Avg Latency: {result.avg_latency_ms:.0f}ms\n"
            f"{'='*60}"
        )

    return result


async def run_retrieval_compare(
    strategies: List[StrategyName] = None,
    k_values: List[int] = None,
    verbose: bool = True,
) -> RetrievalCompareReport:
    """
    对比多种检索策略。

    Args:
        strategies: 要对比的策略列表，默认全部
        k_values: K 值列表
        verbose: 详细输出

    Returns:
        RetrievalCompareReport
    """
    if strategies is None:
        strategies = ["vector_only", "hybrid", "hybrid_rerank"]

    report = RetrievalCompareReport()
    for strat in strategies:
        logger.info(f"\n--- 运行策略: {STRATEGIES[strat]['name']} ---")
        result = await run_retrieval_eval(strategy=strat, k_values=k_values, verbose=verbose)
        report.results.append(result)

    # 打印对比表
    if verbose and len(report.results) >= 2:
        _print_compare_table(report)

    return report


def _print_compare_table(report: RetrievalCompareReport):
    """打印策略对比表格"""
    header = f"{'指标':<18}"
    for r in report.results:
        header += f" {STRATEGIES[r.strategy]['name']:<20}"
    lines = [header, "-" * len(header)]

    metrics = [
        ("Recall@5", "recall_5", ".1%"),
        ("Recall@10", "recall_10", ".1%"),
        ("Precision@5", "precision_5", ".1%"),
        ("MRR", "mrr", ".3f"),
        ("NDCG@5", "ndcg_5", ".3f"),
        ("Hit Rate@5", "hit_rate_5", ".1%"),
        ("Avg Latency", "avg_latency_ms", ".0fms"),
    ]

    for label, attr, fmt in metrics:
        row = f"{label:<18}"
        for r in report.results:
            val = getattr(r, attr, 0)
            if fmt == ".1%":
                row += f" {val:.1%}".ljust(21)
            elif fmt == ".3f":
                row += f" {val:.3f}".ljust(21)
            elif fmt == ".0fms":
                row += f" {val:.0f}ms".ljust(21)
            else:
                row += f" {val}".ljust(21)
        lines.append(row)

    logger.info("\n" + "\n".join(lines))


# ============================================================
# CLI 入口
# ============================================================

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    strategy = "all"
    if len(sys.argv) > 1 and "--strategy" in sys.argv:
        idx = sys.argv.index("--strategy")
        if idx + 1 < len(sys.argv):
            strategy = sys.argv[idx + 1]

    async def main():
        if strategy == "all":
            await run_retrieval_compare()
        else:
            await run_retrieval_eval(strategy=strategy)

    asyncio.run(main())
