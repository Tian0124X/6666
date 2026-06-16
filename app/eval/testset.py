"""
内置评测数据集 — 覆盖企业办公常见场景

2026 升级: 增加 ground_truth 字段支持 RAGAS 标准评测

格式:
  - question: 用户问题
  - keywords: 关键词 (快速模式用)
  - ground_truth: 标准答案 (RAGAS 模式用)
  - category: 问题分类
  - difficulty: easy / medium / hard
"""

RAG_TESTSET = [
    # === 制度类 ===
    {
        "id": "Q001",
        "question": "公司年假有多少天？",
        "keywords": ["年假", "天", "工龄"],
        "ground_truth": "公司员工根据工龄享有不同天数的年假：工龄1-10年享有5天年假，10-20年享有10天年假，20年以上享有15天年假。年假需提前一周申请，经部门主管审批。",
        "category": "制度查询",
        "difficulty": "easy",
    },
    {
        "id": "Q002",
        "question": "员工加班费怎么计算？",
        "keywords": ["加班", "工资", "小时", "倍"],
        "ground_truth": "加班费按以下标准计算：工作日加班按正常工资的1.5倍计算，休息日加班按2倍计算，法定节假日加班按3倍计算。加班需提前申请并经审批，每月加班时长不得超过36小时。",
        "category": "制度查询",
        "difficulty": "easy",
    },
    {
        "id": "Q003",
        "question": "病假需要提供什么证明材料？",
        "keywords": ["病假", "医院", "证明", "请假"],
        "ground_truth": "请病假需提供以下材料：1）二级甲等以上医院开具的病假证明或诊断书；2）病历本复印件；3）药品处方单或缴费凭证。病假3天以内可事后补交，3天以上需提前提交。病假期间工资按基本工资的60%发放。",
        "category": "制度查询",
        "difficulty": "medium",
    },
    {
        "id": "Q004",
        "question": "公司对于远程办公有什么规定？",
        "keywords": ["远程", "居家", "办公", "申请"],
        "ground_truth": "公司远程办公规定：员工每月最多可申请5天远程办公，需提前2天在OA系统提交远程办公申请，经直属主管审批。远程办公期间需保持在线（9:00-18:00）并及时响应工作消息。核心岗位（涉及保密数据）不得远程办公。",
        "category": "制度查询",
        "difficulty": "medium",
    },
    {
        "id": "Q005",
        "question": "员工离职需要提前多久通知？交接流程是什么？",
        "keywords": ["离职", "通知", "交接", "流程", "天"],
        "ground_truth": "正式员工离职需提前30天书面通知，试用期员工提前3天。交接流程包括：1）提交离职申请书；2）部门主管审批；3）HR面谈；4）工作交接清单签署（包括文档、账号、设备、客户关系等）；5）财务结算；6）办理离职手续。全部流程约需2-4周。",
        "category": "制度查询",
        "difficulty": "hard",
    },
    # === 数据类 ===
    {
        "id": "Q006",
        "question": "今年第一季度的销售额是多少？",
        "keywords": ["季度", "销售", "额", "Q1"],
        "ground_truth": "今年第一季度（1月-3月）公司总销售额为1850万元，同比增长12.5%。其中1月580万、2月520万、3月750万。主要增长来自互联网和金融行业客户，产品A贡献最大约占40%。",
        "category": "数据分析",
        "difficulty": "medium",
    },
    {
        "id": "Q007",
        "question": "对比去年和今年的客户增长率",
        "keywords": ["增长", "客户", "同比", "去年"],
        "ground_truth": "今年客户总量较去年增长18.5%。新增客户320家，其中A级客户增长10%（新增8家），B级客户增长22%（新增45家），C级客户增长17%。客户流失率从去年的8.2%下降到6.5%。增长最快的行业是互联网（+35%）和新能源（+28%）。",
        "category": "数据分析",
        "difficulty": "hard",
    },
    # === OA/CRM类 ===
    {
        "id": "Q008",
        "question": "张三的请假审批通过了没有？",
        "keywords": ["张三", "请假", "审批", "通过"],
        "ground_truth": "张三最近提交了年假申请（OA-001），审批状态为已通过，审批人为部门主管李四，审批时间为2026年6月10日，请假天数为3天。",
        "category": "OA查询",
        "difficulty": "easy",
    },
    {
        "id": "Q009",
        "question": "列出所有A级客户",
        "keywords": ["A级", "客户", "列表"],
        "ground_truth": "公司目前有A级客户2家：ABC科技有限公司（互联网行业，合同额500万，联系人赵总13800001001）和DEF信息技术（互联网行业，合同额450万，联系人李总13800001004）。A级客户定义为年合同额超过300万且合作年限3年以上的客户。",
        "category": "CRM查询",
        "difficulty": "easy",
    },
    {
        "id": "Q010",
        "question": "最近一周有多少审批被驳回？原因是什么？",
        "keywords": ["驳回", "审批", "原因", "一周"],
        "ground_truth": "最近一周共有2条审批被驳回：1）OA-004采购申请（申请人赵六），驳回原因：预算超出部门限额，需重新审批；2）OA-007出差申请（申请人王五），驳回原因：出差目的地和行程说明不够详细。整体驳回率为15%。",
        "category": "OA查询",
        "difficulty": "hard",
    },
]

# Agent 评测用例 (不变)
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
