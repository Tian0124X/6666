"""响应体 Pydantic 模型"""

from pydantic import BaseModel, Field
from typing import Any


class HealthResponse(BaseModel):
    status: str
    version: str
    llm_model: str


class ChatResponse(BaseModel):
    answer: str
    task_type: str = "simple"


class KnowledgeQAResponse(BaseModel):
    answer: str
    sources: list[dict] = []
    mode: str = ""           # standard / agentic / graphrag / direct
    level: int = -1          # 自适应复杂度等级
    from_cache: bool = False # 是否命中缓存
    iterations: int = 1      # Agentic RAG 迭代轮数
    timings_ms: dict[str, float] = Field(default_factory=dict)


class ToolListResponse(BaseModel):
    tools: list[dict]


class ToolAnalyzeResponse(BaseModel):
    result: str


class UploadResponse(BaseModel):
    status: str
    filename: str
    chunks: int
    message: str


class ErrorResponse(BaseModel):
    detail: str
