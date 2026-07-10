"""请求体 Pydantic 模型"""

from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """POST /api/chat 请求体"""
    message: str = Field(..., description="用户消息", min_length=1, max_length=10000)
    session_id: str = Field(default="default", description="会话 ID")
    user_id: str = Field(
        default="",
        description="[DEPRECATED] 用户 ID 现在从 Bearer token 推导，此字段被忽略。保留以兼容旧客户端。"
    )
    with_chart: bool = Field(default=True, description="是否生成图表（数据对话专用）")
    mode: Literal["auto", "rag"] = Field(
        default="auto",
        description="对话模式：auto 自动路由，rag 强制知识库检索",
    )


class KnowledgeQARequest(BaseModel):
    """POST /api/knowledge/qa 请求体"""
    question: str = Field(..., description="问题", min_length=1)
    top_k: int = Field(default=5, ge=1, le=20, description="检索文档数")


class ToolAnalyzeRequest(BaseModel):
    """POST /api/tools/analyze 请求体"""
    file_path: str = Field(..., description="文件路径")
    action: str = Field(default="summary", description="summary | analyze | full_report")
    target_column: str | None = Field(default=None, description="目标列名")
    chart_type: str | None = Field(default=None, description="bar | line | pie | scatter")
