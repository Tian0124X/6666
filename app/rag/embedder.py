"""BGE 向量化模块 — 线程安全懒加载 + HuggingFace 离线容错"""

import os
import logging
import threading
from typing import List
from langchain_core.embeddings import Embeddings

logger = logging.getLogger(__name__)

# HuggingFace 镜像（国内加速），可通过 HF_ENDPOINT 环境变量覆盖
_HF_MIRROR = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")


class BGEEmbeddings(Embeddings):
    """
    BGE-Small-ZH 向量化，LangChain 兼容封装。

    BGE 模型关键细节（BAAI 官方）：
    - 文档侧加前缀: "为这个句子生成表示以用于检索相关文章："
    - 查询侧不加前缀
    - 差异影响 3-5% 召回率

    线程安全：懒加载 + 锁，避免多请求并发加载。
    lifespan 预热后在 executor 中加载，不阻塞事件循环。

    HuggingFace 容错：优先本地缓存，网络不通时离线加载。
    """

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        self.model_name = model_name
        self._model = None
        self._dim = None
        self._lock = threading.Lock()

    @property
    def model(self):
        """线程安全懒加载，离线优先以避免 HuggingFace 网络不可达"""
        if self._model is not None:
            return self._model

        with self._lock:
            if self._model is not None:
                return self._model
            from sentence_transformers import SentenceTransformer

            # 策略：优先本地缓存 → 镜像 → 直连 HuggingFace
            for strategy, kwargs in [
                ("local_cache", {"local_files_only": True}),
                ("hf_mirror", {"local_files_only": False}),
            ]:
                try:
                    if strategy == "hf_mirror":
                        # 使用国内镜像加速
                        os.environ.setdefault("HF_ENDPOINT", _HF_MIRROR)

                    logger.info(f"加载 BGE 模型: {self.model_name} (策略: {strategy})...")
                    self._model = SentenceTransformer(self.model_name, **kwargs)
                    self._dim = self._model.get_embedding_dimension()
                    logger.info(f"BGE 模型就绪 ({self._dim}维, 策略: {strategy})")
                    break
                except Exception as e:
                    logger.debug(f"BGE 加载失败 ({strategy}): {e}")
                    if strategy == "local_cache":
                        continue
                    raise

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
