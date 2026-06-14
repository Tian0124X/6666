"""工具基类 + 全局注册中心"""

import logging
from typing import Dict, Type, Optional
from pydantic import BaseModel
from langchain_core.tools import BaseTool as LangChainBaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册中心（单例模式）"""

    _instance: Optional["ToolRegistry"] = None
    _tools: Dict[str, Type[LangChainBaseTool]] = {}
    _instances: Dict[str, LangChainBaseTool] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, tool_cls: Type[LangChainBaseTool], override: bool = False):
        """注册工具类"""
        try:
            instance = tool_cls()
            name = instance.name
        except Exception:
            name = tool_cls.__name__

        if name in self._tools and not override:
            logger.warning(f"工具 '{name}' 已注册，跳过（override=True 可覆盖）")
            return
        self._tools[name] = tool_cls
        logger.info(f"✅ 工具已注册: {name}")

    def unregister(self, name: str):
        """注销工具"""
        self._tools.pop(name, None)
        self._instances.pop(name, None)
        logger.info(f"🗑 工具已注销: {name}")

    def get_tool(self, name: str) -> Optional[LangChainBaseTool]:
        """获取工具实例（懒加载）"""
        if name not in self._tools:
            return None
        if name not in self._instances:
            self._instances[name] = self._tools[name]()
        return self._instances[name]

    def list_tools(self) -> list[LangChainBaseTool]:
        """获取所有已注册工具实例"""
        return [self.get_tool(n) for n in self._tools]

    def list_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def get_tools_description(self) -> str:
        """生成工具列表描述（供 LLM Prompt 使用）"""
        lines = []
        for name in self._tools:
            tool = self.get_tool(name)
            if tool:
                lines.append(f"- {name}: {tool.description}")
        return "\n".join(lines)


# 全局单例
registry = ToolRegistry()


def register_tool(cls):
    """装饰器：自动注册工具到全局注册中心"""
    registry.register(cls)
    return cls
