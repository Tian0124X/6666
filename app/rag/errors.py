"""RAG 存储异常，供 API 层映射为明确的 HTTP 响应。"""


class KnowledgeStoreUnavailable(RuntimeError):
    """没有可用且兼容的向量后端时抛出。"""


class EmbeddingDimensionMismatch(RuntimeError):
    """索引的嵌入维度与当前模型不一致时抛出。"""
