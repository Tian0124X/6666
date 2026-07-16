"""可版本化的 RAG 金标集加载器。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_golden_dataset(path: str | Path) -> list[dict[str, Any]]:
    """加载 JSONL 金标集，并在运行检索前验证最小字段。"""
    dataset_path = Path(path)
    samples: list[dict[str, Any]] = []
    with dataset_path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            content = line.strip()
            if not content:
                continue
            try:
                sample = json.loads(content)
            except json.JSONDecodeError as exc:
                raise ValueError(f"金标集第 {line_number} 行不是合法 JSON") from exc
            if not isinstance(sample.get("id"), str) or not sample["id"].strip():
                raise ValueError(f"金标集第 {line_number} 行缺少 id")
            if not isinstance(sample.get("question"), str) or not sample["question"].strip():
                raise ValueError(f"金标集第 {line_number} 行缺少 question")
            relevant_docs = sample.get("relevant_docs", [])
            if not isinstance(relevant_docs, list) or not all(isinstance(item, str) for item in relevant_docs):
                raise ValueError(f"金标集第 {line_number} 行的 relevant_docs 必须是字符串数组")
            sample.setdefault("relevance_grades", {})
            sample.setdefault("expected_refusal", False)
            expected_terms = sample.setdefault("expected_answer_terms", [])
            if not isinstance(expected_terms, list) or not all(
                (isinstance(item, str) and item.strip())
                or (isinstance(item, list) and item and all(isinstance(term, str) and term.strip() for term in item))
                for item in expected_terms
            ):
                raise ValueError(f"金标集第 {line_number} 行的 expected_answer_terms 必须是字符串或同义词组数组")
            expected_citations = sample.setdefault("expected_citation_documents", relevant_docs)
            if not isinstance(expected_citations, list) or not all(
                isinstance(item, str) for item in expected_citations
            ):
                raise ValueError(f"金标集第 {line_number} 行的 expected_citation_documents 必须是字符串数组")
            if sample["expected_refusal"] and (expected_terms or expected_citations):
                raise ValueError(f"金标集第 {line_number} 行的拒答样本不能声明答案词或引用文档")
            samples.append(sample)
    if not samples:
        raise ValueError("金标集为空，至少需要一条样本")
    return samples
