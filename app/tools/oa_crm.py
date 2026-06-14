"""OA/CRM 对接工具 — Mock/Real 双模式，外部 API 不可用时自动降级"""

import logging
from typing import Optional, Literal
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
import httpx
from app.config import settings
from app.tools.base import register_tool

logger = logging.getLogger(__name__)

# ====== Mock 数据 ======
MOCK_OA_APPROVALS = [
    {"id": "OA-001", "title": "年假申请", "status": "已通过", "applicant": "张三", "date": "2026-06-10"},
    {"id": "OA-002", "title": "报销申请", "status": "审批中", "applicant": "李四", "date": "2026-06-11"},
    {"id": "OA-003", "title": "出差申请", "status": "已通过", "applicant": "王五", "date": "2026-06-09"},
    {"id": "OA-004", "title": "采购申请", "status": "已驳回", "applicant": "赵六", "date": "2026-06-08"},
    {"id": "OA-005", "title": "加班申请", "status": "已通过", "applicant": "张三", "date": "2026-06-12"},
]

MOCK_CRM_CUSTOMERS = [
    {"id": "CRM-001", "name": "ABC科技有限公司", "industry": "互联网", "level": "A", "contact": "赵总", "phone": "13800001001"},
    {"id": "CRM-002", "name": "XYZ实业集团", "industry": "制造业", "level": "B", "contact": "钱总", "phone": "13800001002"},
    {"id": "CRM-003", "name": "123商贸公司", "industry": "零售", "level": "C", "contact": "孙总", "phone": "13800001003"},
    {"id": "CRM-004", "name": "DEF信息技术", "industry": "互联网", "level": "A", "contact": "李总", "phone": "13800001004"},
    {"id": "CRM-005", "name": "GHI新能源", "industry": "能源", "level": "B", "contact": "周总", "phone": "13800001005"},
]
# ====================


class OAQueryInput(BaseModel):
    action: Literal["list_approvals", "query_by_id", "query_by_user", "query_by_status"]
    value: Optional[str] = Field(default=None, description="查询值")


class CRMQueryInput(BaseModel):
    action: Literal["list_customers", "query_by_id", "query_by_industry", "query_by_level"]
    value: Optional[str] = Field(default=None, description="查询值")


# ====== OA Tool ======
@register_tool
class OATool(BaseTool):
    """OA 审批查询工具"""
    name: str = "oa_query"
    description: str = (
        "查询 OA 审批状态。支持 list_approvals(全部列表)、query_by_id(按ID)、"
        "query_by_user(按申请人)、query_by_status(按状态：已通过/审批中/已驳回)。"
        "外部 API 不可用时自动使用 Mock 数据。"
    )
    args_schema: type[BaseModel] = OAQueryInput

    def _query_real(self, action: str, value: Optional[str]) -> str:
        """真实 OA API 调用"""
        if not settings.OA_API_URL:
            raise ValueError("OA_API_URL 未配置")
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                f"{settings.OA_API_URL}/approvals",
                params={"action": action, "value": value or ""},
            )
            resp.raise_for_status()
            return resp.text

    def _query_mock(self, action: str, value: Optional[str]) -> str:
        """Mock 数据查询"""
        if action == "list_approvals":
            items = MOCK_OA_APPROVALS
        elif action == "query_by_id":
            items = [a for a in MOCK_OA_APPROVALS if a["id"].upper() == value.upper()] if value else []
        elif action == "query_by_user":
            items = [a for a in MOCK_OA_APPROVALS if value and value in a["applicant"]]
        elif action == "query_by_status":
            items = [a for a in MOCK_OA_APPROVALS if value and value in a["status"]]
        else:
            items = MOCK_OA_APPROVALS

        if not items:
            return "未找到匹配的审批记录。"

        lines = ["## OA 审批记录"]
        for item in items:
            emoji = {"已通过": "✅", "审批中": "⏳", "已驳回": "❌"}.get(item["status"], "")
            lines.append(
                f"- {emoji} [{item['id']}] {item['title']} "
                f"| {item['status']} | 申请人: {item['applicant']} | {item['date']}"
            )
        return "\n".join(lines)

    def _run(self, action: str = "list_approvals", value: Optional[str] = None) -> str:
        try:
            return self._query_real(action, value)
        except Exception as e:
            logger.warning(f"OA API 不可用，降级到 Mock: {e}")
            return f"[Mock] \n{self._query_mock(action, value)}"


# ====== CRM Tool ======
@register_tool
class CRMTool(BaseTool):
    """CRM 客户查询工具"""
    name: str = "crm_query"
    description: str = (
        "查询 CRM 客户信息。支持 list_customers(全部客户)、query_by_id(按ID)、"
        "query_by_industry(按行业)、query_by_level(按客户等级 A/B/C)。"
        "外部 API 不可用时自动使用 Mock 数据。"
    )
    args_schema: type[BaseModel] = CRMQueryInput

    def _query_real(self, action: str, value: Optional[str]) -> str:
        """真实 CRM API 调用"""
        if not settings.CRM_API_URL:
            raise ValueError("CRM_API_URL 未配置")
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                f"{settings.CRM_API_URL}/customers",
                params={"action": action, "value": value or ""},
            )
            resp.raise_for_status()
            return resp.text

    def _query_mock(self, action: str, value: Optional[str]) -> str:
        """Mock 数据查询"""
        if action == "list_customers":
            items = MOCK_CRM_CUSTOMERS
        elif action == "query_by_id":
            items = [c for c in MOCK_CRM_CUSTOMERS if value and c["id"].upper() == value.upper()]
        elif action == "query_by_industry":
            items = [c for c in MOCK_CRM_CUSTOMERS if value and value in c["industry"]]
        elif action == "query_by_level":
            items = [c for c in MOCK_CRM_CUSTOMERS if value and c["level"].upper() == value.upper()]
        else:
            items = MOCK_CRM_CUSTOMERS

        if not items:
            return "未找到匹配的客户信息。"

        lines = ["## CRM 客户信息"]
        level_icon = {"A": "⭐", "B": "🌟", "C": "💼"}
        for item in items:
            icon = level_icon.get(item["level"], "")
            lines.append(
                f"- {icon} [{item['id']}] {item['name']} "
                f"| {item['industry']} | {item['level']}级 "
                f"| 联系人: {item['contact']} ({item['phone']})"
            )
        return "\n".join(lines)

    def _run(self, action: str = "list_customers", value: Optional[str] = None) -> str:
        try:
            return self._query_real(action, value)
        except Exception as e:
            logger.warning(f"CRM API 不可用，降级到 Mock: {e}")
            return f"[Mock] \n{self._query_mock(action, value)}"
