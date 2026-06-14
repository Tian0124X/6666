"""
智能文本分块 — 借鉴 RAGFlow 模板化分块策略

2026 最佳实践: 不同文档类型使用不同策略
- PDF: 按页 + 段落边界 (保留页码元数据)
- Word: 按段落 + 标题层级 (保留结构信息)
- Excel: 按 Sheet + 行 (保留列名语义)
- 代码: AST-aware (保留函数/类边界)
- 通用: 递归字符分割 (中文优化)
"""

import logging
from typing import List, Optional
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


# ====== 分块策略预设 (借鉴 RAGFlow template-based chunking) ======

CHUNK_PRESETS = {
    "pdf": {
        "chunk_size": 800,
        "chunk_overlap": 200,
        "separators": ["\n\n", "\n", "。", "；", "，", ". ", "; ", ", ", " "],
        "description": "PDF 文档: 大块 800 + 高重叠 200，保留段落完整性",
    },
    "docx": {
        "chunk_size": 600,
        "chunk_overlap": 150,
        "separators": ["\n\n", "\n", "。", "；", "，", ". ", "; ", ", ", " "],
        "description": "Word 文档: 中块 600，按段落+标题层级",
    },
    "excel": {
        "chunk_size": 400,
        "chunk_overlap": 50,
        "separators": ["\n", " | ", "。", "；", ","],
        "description": "Excel: 小块 400 + 低重叠，按行+列名",
    },
    "txt": {
        "chunk_size": 500,
        "chunk_overlap": 150,
        "separators": ["\n\n", "\n", "。", "；", "，", ". ", "; ", ", ", " "],
        "description": "TXT/CSV: 标准 500，中文优化",
    },
    "code": {
        "chunk_size": 1000,
        "chunk_overlap": 100,
        "separators": ["\n\n", "\n", ";", " "],
        "description": "代码: 大块 1000 + 低重叠，按函数/类边界",
    },
    "default": {
        "chunk_size": 500,
        "chunk_overlap": 150,
        "separators": ["\n\n", "\n", "。", "；", "，", ". ", "; ", ", ", " "],
        "description": "通用: 标准中文优化",
    },
}


def get_preset_for_type(file_type: str) -> dict:
    """根据文档类型选择最佳分块策略"""
    file_type = file_type.lower().lstrip(".")
    if file_type in ("pdf",):
        return CHUNK_PRESETS["pdf"]
    if file_type in ("docx", "doc"):
        return CHUNK_PRESETS["docx"]
    if file_type in ("xlsx", "xls", "csv"):
        return CHUNK_PRESETS["excel"]
    if file_type in ("py", "js", "ts", "java", "go", "rs", "cpp", "c", "sh"):
        return CHUNK_PRESETS["code"]
    return CHUNK_PRESETS["default"]


def create_splitter_for_document(doc: Document, file_type: Optional[str] = None) -> RecursiveCharacterTextSplitter:
    """
    根据文档元数据自动选择最优分块策略 (RAGFlow 风格)。

    Args:
        doc: 要分块的文档
        file_type: 文档类型 (pdf/docx/xlsx/txt/code)，不传则从 metadata 推断

    Returns:
        配置好的 RecursiveCharacterTextSplitter
    """
    if file_type is None:
        file_type = doc.metadata.get("file_type", "default")
    preset = get_preset_for_type(file_type)
    logger.info(f"分块策略: {file_type} → {preset['description']}")
    return RecursiveCharacterTextSplitter(
        chunk_size=preset["chunk_size"],
        chunk_overlap=preset["chunk_overlap"],
        separators=preset["separators"],
    )


def create_chinese_splitter(
    chunk_size: int = 500,
    chunk_overlap: int = 150,
) -> RecursiveCharacterTextSplitter:
    """
    创建中文优化的递归分块器 (兼容旧接口)。

    分隔符优先级（从高到低）：
    1. 段落边界 \\n\\n
    2. 换行 \\n
    3. 中文标点（句号、分号、逗号）
    4. 英文标点
    5. 空格
    6. 字符级（最后手段）
    """
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=[
            "\n\n",    # 段落边界
            "\n",      # 换行
            "。",      # 中文句号
            "！",      # 中文感叹号
            "？",      # 中文问号
            "；",      # 中文分号
            "，",      # 中文逗号
            ".",       # 英文句号
            "!",       # 英文感叹号
            "?",       # 英文问号
            ";",       # 英文分号
            " ",       # 空格
            "",        # 字符级
        ],
        length_function=len,
    )


def split_documents(
    documents: List[Document],
    chunk_size: int = 500,
    chunk_overlap: int = 150,
) -> List[Document]:
    """
    将文档列表分块。

    每个 chunk 保留原始元数据，并附加：
    - chunk_id: 序号
    - chunk_preview: 前 100 字符预览
    """
    splitter = create_chinese_splitter(chunk_size, chunk_overlap)
    chunks = splitter.split_documents(documents)

    # 丰富元数据
    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_id"] = i
        chunk.metadata["chunk_preview"] = chunk.page_content[:100]

    return chunks


# 不同场景推荐参数
PRESETS = {
    "short_qa":   {"chunk_size": 300, "chunk_overlap": 80},    # 短问答（FAQ/制度条款）
    "general":    {"chunk_size": 500, "chunk_overlap": 150},   # 通用文档
    "long_doc":   {"chunk_size": 800, "chunk_overlap": 200},   # 长文档（报告/手册）
    "excel":      {"chunk_size": 2000, "chunk_overlap": 100},  # Excel（每 sheet 已是大块）
}
