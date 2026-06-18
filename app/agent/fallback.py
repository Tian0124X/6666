"""规则引擎降级 — LLM 不可用时的预定义计划模板

2026: 复用 app.agent.intent 统一意图识别，避免重复维护关键词表
"""

from app.agent.intent import classify_intent, Intent, extract_file_path

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

# 意图 → 计划 key 的映射
INTENT_PLAN_MAP = {
    Intent.DATA_ANALYSIS: "data_conversation",
    Intent.DATA_REPORT: "data_report",
    Intent.OA_QUERY: "oa_query",
    Intent.CRM_QUERY: "crm_query",
    Intent.KNOWLEDGE_QA: "knowledge_qa",
    Intent.GENERAL_CHAT: "knowledge_qa",  # 兜底
    Intent.GREETING: "knowledge_qa",      # 兜底
    Intent.MULTI_DOMAIN: "data_report",   # 跨领域走报告模板
}


def rule_based_plan(user_input: str) -> dict:
    """基于统一意图识别生成降级计划"""
    intent = classify_intent(user_input)
    plan_key = INTENT_PLAN_MAP.get(intent.primary, "knowledge_qa")
    plan = dict(PREDEFINED_PLANS[plan_key])  # 浅拷贝

    # 数据对话: 注入 file_path
    if plan_key == "data_conversation":
        fp = extract_file_path(user_input)
        if fp and plan.get("tasks"):
            plan["tasks"][0]["tool_params"]["file_path"] = fp

    return plan
