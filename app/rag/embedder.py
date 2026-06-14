"""BGE 向量化模块 — 2026 最佳实践：文档/查询使用不同前缀"""

import logging
from typing import List
from langchain_core.embeddings import Embeddings

logger = logging.getLogger(__name__)


class BGEEmbeddings(Embeddings):
    """
    BGE-Small-ZH 向量化，LangChain 兼容封装。

    BGE 模型的关键细节（来自 BAAI 官方文档）：
    - 文档侧需要加前缀: "为这个句子生成表示以用于检索相关文章："
    - 查询侧不加前缀
    - 这个差异在 2026 年基准测试中影响 3-5% 的召回率

    模型在首次调用时懒加载（避免 torch 阻塞应用启动）。
    """

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        self.model_name = model_name
        self._model = None
        self._dim = None

    @property
    def model(self):
        """懒加载模型"""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"正在加载 BGE 模型: {self.model_name}...")
            self._model = SentenceTransformer(self.model_name)
            self._dim = self._model.get_embedding_dimension()
            logger.info(f"BGE 模型就绪 (维度: {self._dim})")
        return self._model

    @property
    def dimension(self) -> int:
        if self._dim is None:
            _ = self.model  # 触发懒加载
        return self._dim or 512

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量向量化文档 — 加前缀（含空列表保护）"""
        if not texts:
            return []
        texts_with_prefix = [
            f"为这个句子生成表示以用于检索相关文章：{t}" for t in texts
        ]
        embeddings = self.model.encode(
            texts_with_prefix,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> List[float]:
        """向量化查询 — 不加前缀"""
        embedding = self.model.encode(
            text,
            normalize_embeddings=True,
        )
        return embedding.tolist()
