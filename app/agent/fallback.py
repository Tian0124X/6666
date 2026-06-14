"""规则引擎降级 — LLM 不可用时的预定义计划模板"""

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
    (r"分析.*生成.*报告|数据.*报告|报表|生成.*报告", "data_report"),
    (r"分析.*数据|数据.*分析|统计|图表", "data_analysis"),
    (r"审批|OA|请假|报销|出差", "oa_query"),
    (r"客户|CRM|客户信息|客户列表", "crm_query"),
    (r"知识|文档|制度|规定|手册|帮助|怎么|如何|什么", "knowledge_qa"),
]


def rule_based_plan(user_input: str) -> dict:
    for pattern, plan_key in RULE_TABLE:
        if re.search(pattern, user_input):
            return PREDEFINED_PLANS[plan_key]
    return PREDEFINED_PLANS["knowledge_qa"]
