"""BGE 向量化模块 — 线程安全懒加载 + HuggingFace 离线容错"""

import os
import logging
import threading
from typing import List
from langchain_core.embeddings import Embeddings
from app.config import settings

logger = logging.getLogger(__name__)

# HuggingFace 镜像（国内加速），可通过 HF_ENDPOINT 环境变量覆盖
_HF_MIRROR = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")
_shared_embedder: "BGEEmbeddings | None" = None
_shared_embedder_lock = threading.Lock()


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

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.RAG_EMBEDDING_MODEL
        self._model = None
        self._dim = None
        self._lock = threading.Lock()

    @property
    def model(self):
        """线程安全懒加载，本地路径优先，绕过 HuggingFace 网络依赖"""
        if self._model is not None:
            return self._model

        with self._lock:
            if self._model is not None:
                return self._model
            from sentence_transformers import SentenceTransformer

            # SentenceTransformers 会在各个平台使用 Hugging Face 标准缓存。
            # 旧版硬编码 /root 路径，在 Windows 下必然无法命中。
            for strategy, kwargs in [
                ("local_cache", {"local_files_only": True}),
                ("hf_mirror", {"local_files_only": False}),
            ]:
                try:
                    if strategy == "hf_mirror":
                        os.environ.setdefault("HF_ENDPOINT", _HF_MIRROR)

                    logger.info(f"加载 BGE 模型: {self.model_name} (策略: {strategy})...")
                    self._model = SentenceTransformer(self.model_name, **kwargs)

                    self._dim = self._model.get_embedding_dimension()
                    logger.info(f"BGE 模型就绪 ({self._dim}维, 策略: {strategy})")
                    break
                except Exception as e:
                    logger.debug(f"BGE 加载失败 ({strategy}): {e}")
                    if strategy != "hf_mirror":
                        continue
                    raise

        return self._model

    @property
    def dimension(self) -> int:
        if self._dim is None:
            _ = self.model  # 触发懒加载
        return self._dim or 512

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量向量化文档 — BGE-M3 不加前缀"""
        if not texts:
            return []
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> List[float]:
        """向量化查询 — BGE-M3 不加前缀"""
        embedding = self.model.encode(
            text,
            normalize_embeddings=True,
        )
        return embedding.tolist()


def get_embedding_model() -> BGEEmbeddings:
    """返回所有 RAG 组件复用的进程级嵌入模型包装器。"""
    global _shared_embedder
    if _shared_embedder is None:
        with _shared_embedder_lock:
            if _shared_embedder is None:
                _shared_embedder = BGEEmbeddings()
    return _shared_embedder
