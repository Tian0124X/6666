"""BGE 向量化模块 — 线程安全懒加载"""

import logging
import threading
from typing import List
from langchain_core.embeddings import Embeddings

logger = logging.getLogger(__name__)


class BGEEmbeddings(Embeddings):
    """
    BGE-Small-ZH 向量化，LangChain 兼容封装。

    BGE 模型关键细节（BAAI 官方）：
    - 文档侧加前缀: "为这个句子生成表示以用于检索相关文章："
    - 查询侧不加前缀
    - 差异影响 3-5% 召回率

    线程安全：懒加载 + 锁，避免多请求并发加载。
    lifespan 预热后在 executor 中加载，不阻塞事件循环。
    """

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        self.model_name = model_name
        self._model = None
        self._dim = None
        self._lock = threading.Lock()

    @property
    def model(self):
        """线程安全懒加载"""
        if self._model is not None:
            return self._model

        with self._lock:
            if self._model is not None:
                return self._model
            from sentence_transformers import SentenceTransformer
            logger.info(f"加载 BGE 模型: {self.model_name} (首次, ~20s)...")
            self._model = SentenceTransformer(self.model_name)
            self._dim = self._model.get_embedding_dimension()
            logger.info(f"BGE 模型就绪 ({self._dim}维)")

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
