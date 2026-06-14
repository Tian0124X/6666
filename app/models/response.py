"""响应体 Pydantic 模型"""

from pydantic import BaseModel
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
