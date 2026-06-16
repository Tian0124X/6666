"""规则引擎降级 — LLM 不可用时的预定义计划模板

2026: 支持数据对话 — 从消息中提取文件路径并路由到 data_conversation
"""

import re

PREDEFINED_PLANS = {
    "data_report": {
        "tasks": [
            {"task_id": "task_1", "description": "读取并分析数据文件", "tool_name": "data_analyzer", "tool_params": {"action": "analyze"}, "depends_on": []},
            {"task_id": "task_2", "description": "生成数据分析报告", "tool_name": "data_analyzer", "tool_params": {"action": "full_report"}, "depends_on": ["task_1"]},
        ],
        "execution_order": [["task_1"], ["task_2"]],
    },
    "data_analysis": {
        "tasks": [
            {"task_id": "task_1", "description": "分析数据", "tool_name": "data_analyzer", "tool_params": {"action": "analyze"}, "depends_on": []},
        ],
        "execution_order": [["task_1"]],
    },
    "data_conversation": {
        "tasks": [
            {"task_id": "task_1", "description": "数据对话分析", "tool_name": "data_conversation", "tool_params": {}, "depends_on": []},
        ],
        "execution_order": [["task_1"]],
    },
    "oa_query": {
        "tasks": [
            {"task_id": "task_1", "description": "查询OA审批", "tool_name": "oa_query", "tool_params": {"action": "list_approvals"}, "depends_on": []},
        ],
        "execution_order": [["task_1"]],
    },
    "crm_query": {
        "tasks": [
            {"task_id": "task_1", "description": "查询CRM客户", "tool_name": "crm_query", "tool_params": {"action": "list_customers"}, "depends_on": []},
        ],
        "execution_order": [["task_1"]],
    },
    "knowledge_qa": {
        "tasks": [
            {"task_id": "task_1", "description": "搜索知识库", "tool_name": "knowledge_search", "tool_params": {}, "depends_on": []},
        ],
        "execution_order": [["task_1"]],
    },
}

RULE_TABLE = [
    # 数据对话: 检测已上传文件标记 → 优先使用 data_conversation
    (r"\[已上传数据文件:\s*([^\]]+)\][\s\S]*?(?:分析|统计|查看|显示|计算|对比|画|图表|趋势|分布|汇总|排名|排序|筛选|过滤|最大|最小|平均|求和|多少|几个|哪个|什么|怎么|如何)",
     "data_conversation"),
    (r"分析.*生成.*报告|数据.*报告|报表|生成.*报告", "data_report"),
    (r"分析.*数据|数据.*分析|统计|图表", "data_analysis"),
    (r"审批|OA|请假|报销|出差", "oa_query"),
    (r"客户|CRM|客户信息|客户列表", "crm_query"),
    (r"知识|文档|制度|规定|手册|帮助|怎么|如何|什么", "knowledge_qa"),
]


def extract_file_path(user_input: str) -> str | None:
    """从消息中提取已上传文件的路径"""
    m = re.search(r"\[已上传数据文件:\s*([^\]]+)\]", user_input)
    return m.group(1).strip() if m else None


def rule_based_plan(user_input: str) -> dict:
    """规则匹配计划，如果检测到文件路径则注入 tool_params"""
    for pattern, plan_key in RULE_TABLE:
        if re.search(pattern, user_input):
            plan = dict(PREDEFINED_PLANS[plan_key])  # 浅拷贝
            # 数据对话: 注入 file_path
            if plan_key == "data_conversation":
                fp = extract_file_path(user_input)
                if fp and plan.get("tasks"):
                    plan["tasks"][0]["tool_params"]["file_path"] = fp
            return plan
    return PREDEFINED_PLANS["knowledge_qa"]
