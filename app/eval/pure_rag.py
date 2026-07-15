"""纯 RAG 的离线评测工具。"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import quantiles
from typing import Iterable


@dataclass
class RagEvaluationSample:
    """一条可回放的知识库问答样本。"""

    question: str
    expected_filename: str
    expected_page: int | None = None


def recall_at_k(sources: list[dict], expected_filename: str, k: int = 5) -> float:
    """计算正确文档是否出现在前 k 条证据中。"""
    return float(any(source.get("filename") == expected_filename for source in sources[:k]))


def citation_accuracy(answer: str, sources: list[dict]) -> float:
    """检查回答中出现的引用是否都属于当前证据集合。"""
    import re

    cited = set(re.findall(r"\[(S\d+)\]", answer))
    allowed = {source.get("citation_id") for source in sources}
    return float(bool(cited) and cited.issubset(allowed))


def percentile_95(values: Iterable[float]) -> float:
    """返回性能基准使用的 P95，样本不足时使用最大值。"""
    numbers = sorted(values)
    if not numbers:
        return 0.0
    if len(numbers) < 20:
        return numbers[-1]
    return quantiles(numbers, n=100, method="inclusive")[94]
