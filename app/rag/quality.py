"""知识工程质量报告：让文档是否被正确索引变得可检查。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Sequence

from langchain_core.documents import Document


def _file_sha256(path: Path) -> str:
    """计算原文件版本哈希，供重复上传和问题追溯使用。"""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def build_index_quality_report(
    path: Path,
    documents: Sequence[Document],
    chunks: Sequence[Document],
) -> dict:
    """汇总解析、分块和版本信息，不保存原文内容或用户数据。"""
    document_texts = [document.page_content.strip() for document in documents]
    chunk_texts = [chunk.page_content.strip() for chunk in chunks]
    pages = {
        str(document.metadata["page"])
        for document in documents
        if document.metadata.get("page") is not None
    }
    parsers = sorted({
        str(document.metadata["parser"])
        for document in documents
        if document.metadata.get("parser")
    })
    file_types = sorted({
        str(document.metadata["file_type"])
        for document in documents
        if document.metadata.get("file_type")
    })
    nonempty_chunk_lengths = [len(text) for text in chunk_texts if text]

    return {
        "file_sha256": _file_sha256(path),
        "file_size": path.stat().st_size,
        "document_units": len(documents),
        "page_count": len(pages) if pages else None,
        "source_characters": sum(len(text) for text in document_texts),
        "empty_document_units": sum(1 for text in document_texts if not text),
        "chunks": len(chunks),
        "empty_chunks": sum(1 for text in chunk_texts if not text),
        "average_chunk_characters": round(
            sum(nonempty_chunk_lengths) / len(nonempty_chunk_lengths), 1
        ) if nonempty_chunk_lengths else 0.0,
        "max_chunk_characters": max(nonempty_chunk_lengths, default=0),
        "parsers": parsers,
        "file_types": file_types,
    }
