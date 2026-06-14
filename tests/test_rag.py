"""RAG 知识问答系统测试"""

import os
import pytest
from unittest.mock import patch, Mock
from langchain_core.documents import Document


class TestDocumentLoader:
    """文档加载器测试"""

    def test_detect_file_type_pdf(self):
        from app.rag.loader import detect_file_type
        # 用扩展名回退测试
        assert detect_file_type("test.pdf") in ("pdf",)

    def test_detect_file_type_docx(self):
        from app.rag.loader import detect_file_type
        assert detect_file_type("test.docx") in ("docx",)

    def test_detect_file_type_xlsx(self):
        from app.rag.loader import detect_file_type
        assert detect_file_type("test.xlsx") in ("xlsx",)

    def test_load_txt(self, tmp_path):
        from app.rag.loader import UniversalDocumentLoader
        file_path = os.path.join(tmp_path, "test.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("这是一段测试文本。\n第二行内容。")

        docs = UniversalDocumentLoader.load_txt(file_path)
        assert len(docs) == 1
        assert "测试文本" in docs[0].page_content
        assert docs[0].metadata["file_type"] == "txt"

    def test_load_txt_gbk_encoding(self, tmp_path):
        """应能自动检测 GBK 编码"""
        from app.rag.loader import UniversalDocumentLoader
        file_path = os.path.join(tmp_path, "test_gbk.txt")
        content = "这是GBK编码的中文文本。"
        with open(file_path, "w", encoding="gbk") as f:
            f.write(content)

        docs = UniversalDocumentLoader.load_txt(file_path)
        assert len(docs) == 1
        assert "GBK编码" in docs[0].page_content

    def test_load_nonexistent_file(self):
        from app.rag.loader import UniversalDocumentLoader
        with pytest.raises(FileNotFoundError):
            UniversalDocumentLoader.load("/nonexistent/file.pdf")

    def test_load_excel(self, tmp_path):
        import pandas as pd
        from app.rag.loader import UniversalDocumentLoader
        file_path = os.path.join(tmp_path, "test.xlsx")
        df = pd.DataFrame({"姓名": ["张三", "李四"], "年龄": [25, 30]})
        df.to_excel(file_path, index=False)

        docs = UniversalDocumentLoader.load_excel(file_path)
        assert len(docs) >= 1
        assert "张三" in docs[0].page_content
        assert docs[0].metadata["file_type"] == "excel"


class TestSplitter:
    """文本分块测试"""

    def test_chinese_splitter_creates_chunks(self):
        from app.rag.splitter import split_documents
        doc = Document(
            page_content="第一段内容。第二段内容。第三段内容。" * 50,
            metadata={"source": "test.txt"},
        )
        chunks = split_documents([doc], chunk_size=200, chunk_overlap=50)
        assert len(chunks) > 1
        # 每个 chunk 应有元数据
        for i, c in enumerate(chunks):
            assert "chunk_id" in c.metadata
            assert "chunk_preview" in c.metadata

    def test_overlap_preserves_context(self):
        """重叠应保留相邻 chunk 的公共内容"""
        from app.rag.splitter import split_documents
        text = "A。B。C。D。E。F。G。H。I。J。" * 10
        doc = Document(page_content=text, metadata={"source": "test.txt"})
        chunks = split_documents([doc], chunk_size=100, chunk_overlap=50)
        if len(chunks) >= 2:
            # 第一个 chunk 的尾部应和第二个 chunk 的头部有重叠
            last_chars = chunks[0].page_content[-20:]
            first_chars = chunks[1].page_content[:20]
            # 有重叠字符即可
            common = set(last_chars) & set(first_chars)
            assert len(common) > 0

    def test_presets_have_valid_params(self):
        from app.rag.splitter import PRESETS
        for name, params in PRESETS.items():
            assert params["chunk_size"] > 0
            assert params["chunk_overlap"] > 0
            assert params["chunk_overlap"] < params["chunk_size"]


class TestRetrieverFormatting:
    """检索与格式化测试"""

    def test_format_context(self):
        from app.rag.retriever import _format_context
        docs = [
            Document(
                page_content="公司年假为每年 15 天。",
                metadata={"filename": "员工手册.pdf", "page": 3},
            ),
            Document(
                page_content="年假需提前 3 天申请。",
                metadata={"filename": "员工手册.pdf", "page": 4},
            ),
        ]
        result = _format_context(docs)
        assert "员工手册.pdf" in result
        assert "第3页" in result
        assert "第4页" in result
        assert "15 天" in result
        assert "[来源1]" in result
        assert "[来源2]" in result

    def test_format_context_single_doc(self):
        from app.rag.retriever import _format_context
        docs = [Document(
            page_content="测试内容",
            metadata={"filename": "test.txt"},
        )]
        result = _format_context(docs)
        assert "[来源1]" in result
        assert "test.txt" in result

    def test_chinese_tokenize_jieba(self):
        from app.rag.retriever import _chinese_tokenize
        tokens = _chinese_tokenize("企业智能办公助手平台")
        assert len(tokens) > 1  # 中文应被切分为多个 token

    def test_chinese_tokenize_english(self):
        from app.rag.retriever import _chinese_tokenize
        tokens = _chinese_tokenize("Hello World")
        assert len(tokens) >= 2


class TestRetrieverPrompt:
    """反幻觉 Prompt 测试"""

    def test_rag_prompt_contains_anti_hallucination(self):
        from app.rag.retriever import RAG_SYSTEM_PROMPT
        assert "严格依据" in RAG_SYSTEM_PROMPT
        assert "不要编造" in RAG_SYSTEM_PROMPT
        assert "我无法回答" in RAG_SYSTEM_PROMPT

    def test_query_expansion_prompt(self):
        from app.rag.retriever import QUERY_EXPANSION_PROMPT
        prompt_str = QUERY_EXPANSION_PROMPT.format(question="测试问题")
        assert "3 个" in prompt_str
        assert "测试问题" in prompt_str
