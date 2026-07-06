"""
知识库搜索工具 — 包装 RAG 检索，供 Agent 和回退规划使用。

通过 @register_tool 自动注册到全局 ToolRegistry，
被 app/agent/fallback.py 的 knowledge_qa 回退计划引用。
"""

import logging
from typing import Optional, Type
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.tools.base import register_tool

logger = logging.getLogger(__name__)


class KnowledgeSearchInput(BaseModel):
    query: str = Field(description="搜索查询，自然语言问题")


@register_tool
class KnowledgeSearchTool(BaseTool):
    """搜索企业知识库，返回基于文档的答案"""

    name: str = "knowledge_search"
    description: str = (
        "搜索企业知识库（文档、制度、手册、FAQ 等），"
        "基于 RAG 检索增强生成回答，带来源追溯。"
        "适用于：提问公司制度、查找文档内容、获取操作手册说明。"
    )
    args_schema: Type[BaseModel] = KnowledgeSearchInput

    def _run(self, query: str) -> str:
        """同步入口 — 自动适配运行中/未运行的事件循环"""
        import asyncio
        from app.rag.advanced import smart_rag_qa

        try:
            # 检测是否已有运行中的事件循环
            try:
                loop = asyncio.get_running_loop()
                # 已有事件循环：使用 run_coroutine_threadsafe（会阻塞当前线程）
                import concurrent.futures
                future = asyncio.run_coroutine_threadsafe(
                    smart_rag_qa(question=query),
                    loop,
                )
                result = future.result(timeout=30)
            except RuntimeError:
                # 无运行中的事件循环：直接 asyncio.run
                result = asyncio.run(smart_rag_qa(question=query))

            answer = result.get("answer", "")
            sources = result.get("sources", [])
            if sources:
                source_list = "\n".join(f"  - {s.get('filename', '')}" for s in sources[:5])
                answer += f"\n\n📚 参考来源:\n{source_list}"
            return answer
        except Exception as e:
            logger.error(f"知识库搜索失败: {e}")
            return f"知识库搜索出错: {e}。请稍后重试或换一种问法。"

    async def _arun(self, query: str) -> str:
        """异步入口"""
        from app.rag.advanced import smart_rag_qa

        try:
            result = await smart_rag_qa(question=query)
            answer = result.get("answer", "")
            sources = result.get("sources", [])
            if sources:
                source_list = "\n".join(f"  - {s}" for s in sources[:5])
                answer += f"\n\n📚 参考来源:\n{source_list}"
            return answer
        except Exception as e:
            logger.error(f"知识库搜索失败: {e}")
            return f"知识库搜索出错: {e}。请稍后重试或换一种问法。"
