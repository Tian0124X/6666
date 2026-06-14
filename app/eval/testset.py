"""
内置评测数据集 — 覆盖企业办公常见场景

格式: (question, ground_truth_keywords, expected_sources, difficulty)
- ground_truth_keywords: 回答中应包含的关键词
- expected_sources: 期望引用的文档名列表
- difficulty: easy / medium / hard
"""

RAG_TESTSET = [
    # === 制度类 ===
    {
        "id": "Q001",
        "question": "公司年假有多少天？",
        "keywords": ["年假", "天", "工龄"],
        "category": "制度查询",
        "difficulty": "easy",
    },
    {
        "id": "Q002",
        "question": "员工加班费怎么计算？",
        "keywords": ["加班", "工资", "小时", "倍"],
        "category": "制度查询",
        "difficulty": "easy",
    },
    {
        "id": "Q003",
        "question": "病假需要提供什么证明材料？",
        "keywords": ["病假", "医院", "证明", "请假"],
        "category": "制度查询",
        "difficulty": "medium",
    },
    {
        "id": "Q004",
        "question": "公司对于远程办公有什么规定？",
        "keywords": ["远程", "居家", "办公", "申请"],
        "category": "制度查询",
        "difficulty": "medium",
    },
    {
        "id": "Q005",
        "question": "员工离职需要提前多久通知？交接流程是什么？",
        "keywords": ["离职", "通知", "交接", "流程", "天"],
        "category": "制度查询",
        "difficulty": "hard",
    },
    # === 数据类 ===
    {
        "id": "Q006",
        "question": "今年第一季度的销售额是多少？",
        "keywords": ["季度", "销售", "额", "Q1"],
        "category": "数据分析",
        "difficulty": "medium",
    },
    {
        "id": "Q007",
        "question": "对比去年和今年的客户增长率",
        "keywords": ["增长", "客户", "同比", "去年"],
        "category": "数据分析",
        "difficulty": "hard",
    },
    # === OA/CRM类 ===
    {
        "id": "Q008",
        "question": "张三的请假审批通过了没有？",
        "keywords": ["张三", "请假", "审批", "通过"],
        "category": "OA查询",
        "difficulty": "easy",
    },
    {
        "id": "Q009",
        "question": "列出所有A级客户",
        "keywords": ["A级", "客户", "列表"],
        "category": "CRM查询",
        "difficulty": "easy",
    },
    {
        "id": "Q010",
        "question": "最近一周有多少审批被驳回？原因是什么？",
        "keywords": ["驳回", "审批", "原因", "一周"],
        "category": "OA查询",
        "difficulty": "hard",
    },
]

# Agent 评测用例
AGENT_TESTSET = [
    {
        "id": "A001",
        "task": "查询所有审批记录",
        "expected_tool": "oa_query",
        "expected_action": "list_approvals",
        "difficulty": "easy",
    },
    {
        "id": "A002",
        "task": "分析 data/documents/sales_report.xlsx 并生成摘要",
        "expected_tool": "data_analyzer",
        "expected_action": "summary",
        "difficulty": "medium",
    },
    {
        "id": "A003",
        "task": "查询互联网行业的客户",
        "expected_tool": "crm_query",
        "expected_action": "query_by_industry",
        "difficulty": "easy",
    },
    {
        "id": "A004",
        "task": "公司加班制度是什么？",
        "expected_tool": "knowledge_search",
        "expected_action": "knowledge_search",
        "difficulty": "easy",
    },
    {
        "id": "A005",
        "task": "先查张三的审批记录，再查他的客户信息",
        "expected_tool": "oa_query",
        "expected_action": "query_by_user",
        "difficulty": "hard",
    },
]
