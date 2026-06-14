# 插件化工具系统
from app.tools.base import registry, register_tool
from app.tools.data_analyzer import DataAnalyzerTool
from app.tools.oa_crm import OATool, CRMTool

# 导入即自动注册
# DataAnalyzerTool、OATool、CRMTool 已通过 @register_tool 装饰器注册

__all__ = ["registry", "register_tool", "DataAnalyzerTool", "OATool", "CRMTool"]
