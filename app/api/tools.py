"""工具 API — /api/tools/*"""

from fastapi import APIRouter, HTTPException
from app.models.request import ToolAnalyzeRequest
from app.models.response import ToolListResponse, ToolAnalyzeResponse
from app.tools.base import registry

# 触发工具自动注册
import app.tools.data_analyzer  # noqa
import app.tools.oa_crm  # noqa
import app.tools.knowledge_search  # noqa

router = APIRouter()


@router.get("/list", response_model=ToolListResponse, tags=["工具"])
async def list_tools():
    """获取可用工具列表（从注册中心动态获取）"""
    tools = registry.list_tools()
    return ToolListResponse(
        tools=[{"name": t.name, "description": t.description} for t in tools]
    )


@router.post("/analyze", response_model=ToolAnalyzeResponse, tags=["工具"])
async def analyze_data(req: ToolAnalyzeRequest):
    """数据分析接口"""
    import asyncio
    tool = registry.get_tool("data_analyzer")
    if tool is None:
        raise HTTPException(status_code=503, detail="data_analyzer 工具未注册")

    # 使用线程池执行同步阻塞调用，避免阻塞事件循环
    result = await asyncio.to_thread(
        tool._run,
        file_path=req.file_path,
        action=req.action,
        target_column=req.target_column,
        chart_type=req.chart_type,
    )
    return ToolAnalyzeResponse(result=result)


@router.post("/oa", tags=["工具"])
async def oa_query(action: str = "list_approvals", value: str | None = None):
    """OA 查询接口"""
    import asyncio
    tool = registry.get_tool("oa_query")
    if tool is None:
        raise HTTPException(status_code=503, detail="oa_query 工具未注册")
    result = await asyncio.to_thread(tool._run, action=action, value=value)
    return {"result": result}


@router.post("/crm", tags=["工具"])
async def crm_query(action: str = "list_customers", value: str | None = None):
    """CRM 查询接口"""
    import asyncio
    tool = registry.get_tool("crm_query")
    if tool is None:
        raise HTTPException(status_code=503, detail="crm_query 工具未注册")
    result = await asyncio.to_thread(tool._run, action=action, value=value)
    return {"result": result}
