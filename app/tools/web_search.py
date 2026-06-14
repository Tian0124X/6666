"""
Web 搜索工具 — 借鉴 Dify 50+ built-in tools

为 Agent 提供实时网络搜索能力，补充知识库之外的外部信息。
使用 DuckDuckGo (免费免 Key) 作为默认搜索引擎。
"""

import logging
from typing import Type, Optional
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.tools.base import register_tool

logger = logging.getLogger(__name__)


class WebSearchInput(BaseModel):
    query: str = Field(description="搜索查询词")
    num_results: int = Field(default=5, ge=1, le=10, description="返回结果数量")


@register_tool
class WebSearchTool(BaseTool):
    """网络搜索工具 — 实时获取外部信息"""

    name: str = "web_search"
    description: str = (
        "搜索互联网获取实时信息。适用于：查找最新新闻、查询公开数据、"
        "获取知识库不包含的外部信息。返回结果含标题、摘要和 URL。"
    )
    args_schema: Type[BaseModel] = WebSearchInput

    def _run(self, query: str, num_results: int = 5) -> str:
        """同步搜索 — 尝试 DuckDuckGo → HTTP 降级"""
        try:
            results = self._duckduckgo_search(query, num_results)
            if results:
                return results
        except Exception as e:
            logger.warning(f"DuckDuckGo 搜索失败: {e}")

        # 降级: 返回搜索链接（Agent 可建议用户手动查看）
        return (
            f"⚠️ Web 搜索暂不可用。建议手动搜索:\n"
            f"  - Google: https://www.google.com/search?q={query}\n"
            f"  - Baidu: https://www.baidu.com/s?wd={query}\n"
            f"  - Bing: https://www.bing.com/search?q={query}"
        )

    def _duckduckgo_search(self, query: str, num_results: int = 5) -> Optional[str]:
        """DuckDuckGo 搜索 (免费，无需 API Key)"""
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=num_results))
        if not results:
            return None

        lines = [f"🔍 搜索结果 ({len(results)} 条):"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "无标题")
            body = r.get("body", "")[:200]
            href = r.get("href", "")
            lines.append(f"{i}. **{title}**\n   {body}\n   📎 {href}")
        return "\n\n".join(lines)

    async def _arun(self, query: str, num_results: int = 5) -> str:
        """异步入口"""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._run, query, num_results)
