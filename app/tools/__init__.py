# 插件化工具系统
from app.tools.base import registry, register_tool
from app.tools.data_analyzer import DataAnalyzerTool
from app.tools.data_conversation import DataConversationTool
from app.tools.oa_crm import OATool, CRMTool
from app.tools.knowledge_search import KnowledgeSearchTool
from app.tools.web_search import WebSearchTool

# 导入即自动注册 (通过 @register_tool 装饰器)
# 所有6个工具均已注册: data_analyzer, data_conversation, oa_query, crm_query,
#                         knowledge_search, web_search

__all__ = [
    "registry", "register_tool",
    "DataAnalyzerTool", "DataConversationTool",
    "OATool", "CRMTool",
    "KnowledgeSearchTool", "WebSearchTool",
]
