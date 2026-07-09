"""
内置评测数据集 — 覆盖企业办公常见场景

2026 升级:
  - 增加 relevant_docs 字段（检索测评用）
  - 增加 relevance_grades 字段（NDCG 计算用）
  - 增加 ground_truth 字段支持 RAGAS 标准评测
  - 扩充至 25+ 条，覆盖更多场景和难度

格式:
  - question: 用户问题
  - keywords: 关键词 (快速模式用)
  - ground_truth: 标准答案 (RAGAS 模式用)
  - relevant_docs: 应被检索到的相关文档列表 (检索测评用)
  - relevance_grades: {文档名: 0-3} 相关性分级 (NDCG 用)
  - category: 问题分类
  - difficulty: easy / medium / hard
"""

RAG_TESTSET = [
    # ============================================================
    # 制度类 (Policy) — 8 条
    # ============================================================
    {
        "id": "Q001",
        "question": "公司年假有多少天？",
        "keywords": ["年假", "天", "工龄"],
        "ground_truth": "公司员工根据工龄享有不同天数的年假：工龄1-10年享有5天年假，10-20年享有10天年假，20年以上享有15天年假。年假需提前一周申请，经部门主管审批。",
        "relevant_docs": ["员工手册.pdf", "考勤管理制度.docx"],
        "relevance_grades": {"员工手册.pdf": 3, "考勤管理制度.docx": 2},
        "category": "制度查询",
        "difficulty": "easy",
    },
    {
        "id": "Q002",
        "question": "员工加班费怎么计算？",
        "keywords": ["加班", "工资", "小时", "倍"],
        "ground_truth": "加班费按以下标准计算：工作日加班按正常工资的1.5倍计算，休息日加班按2倍计算，法定节假日加班按3倍计算。加班需提前申请并经审批，每月加班时长不得超过36小时。",
        "relevant_docs": ["薪酬管理制度.pdf", "员工手册.pdf"],
        "relevance_grades": {"薪酬管理制度.pdf": 3, "员工手册.pdf": 1},
        "category": "制度查询",
        "difficulty": "easy",
    },
    {
        "id": "Q003",
        "question": "病假需要提供什么证明材料？",
        "keywords": ["病假", "医院", "证明", "请假"],
        "ground_truth": "请病假需提供以下材料：1）二级甲等以上医院开具的病假证明或诊断书；2）病历本复印件；3）药品处方单或缴费凭证。病假3天以内可事后补交，3天以上需提前提交。病假期间工资按基本工资的60%发放。",
        "relevant_docs": ["考勤管理制度.docx", "员工手册.pdf"],
        "relevance_grades": {"考勤管理制度.docx": 3, "员工手册.pdf": 2},
        "category": "制度查询",
        "difficulty": "medium",
    },
    {
        "id": "Q004",
        "question": "公司对于远程办公有什么规定？",
        "keywords": ["远程", "居家", "办公", "申请"],
        "ground_truth": "公司远程办公规定：员工每月最多可申请5天远程办公，需提前2天在OA系统提交远程办公申请，经直属主管审批。远程办公期间需保持在线（9:00-18:00）并及时响应工作消息。核心岗位（涉及保密数据）不得远程办公。",
        "relevant_docs": ["远程办公管理办法.pdf", "员工手册.pdf"],
        "relevance_grades": {"远程办公管理办法.pdf": 3, "员工手册.pdf": 2},
        "category": "制度查询",
        "difficulty": "medium",
    },
    {
        "id": "Q005",
        "question": "员工离职需要提前多久通知？交接流程是什么？",
        "keywords": ["离职", "通知", "交接", "流程", "天"],
        "ground_truth": "正式员工离职需提前30天书面通知，试用期员工提前3天。交接流程包括：1）提交离职申请书；2）部门主管审批；3）HR面谈；4）工作交接清单签署（包括文档、账号、设备、客户关系等）；5）财务结算；6）办理离职手续。全部流程约需2-4周。",
        "relevant_docs": ["员工手册.pdf", "离职管理办法.docx"],
        "relevance_grades": {"员工手册.pdf": 2, "离职管理办法.docx": 3},
        "category": "制度查询",
        "difficulty": "hard",
    },
    {
        "id": "Q011",
        "question": "新员工试用期多长？考核标准是什么？",
        "keywords": ["试用期", "考核", "新员工", "转正"],
        "ground_truth": "新员工试用期为3个月，表现优异者可提前转正（最短1个月）。考核标准包括：工作能力（40%）、工作态度（30%）、团队协作（20%）、出勤情况（10%）。考核总分80分以上予以转正，60-79分延长试用期1个月，60分以下不予录用。",
        "relevant_docs": ["员工手册.pdf", "绩效考核制度.docx"],
        "relevance_grades": {"员工手册.pdf": 3, "绩效考核制度.docx": 3},
        "category": "制度查询",
        "difficulty": "medium",
    },
    {
        "id": "Q012",
        "question": "出差报销的标准和流程是怎样的？",
        "keywords": ["出差", "报销", "标准", "流程", "发票"],
        "ground_truth": "出差报销标准：交通费实报实销（高铁二等座/飞机经济舱），住宿费一线城市不超过500元/天、其他城市不超过350元/天，餐饮补贴100元/天。报销流程：填写差旅报销单→附发票→部门主管审批→财务审核→5个工作日内打款。",
        "relevant_docs": ["差旅管理制度.pdf", "财务报销流程.docx"],
        "relevance_grades": {"差旅管理制度.pdf": 3, "财务报销流程.docx": 3},
        "category": "制度查询",
        "difficulty": "medium",
    },
    {
        "id": "Q013",
        "question": "公司有哪些培训和发展机会？",
        "keywords": ["培训", "发展", "学习", "晋升", "课程"],
        "ground_truth": "公司提供三类培训：1）入职培训（企业文化+规章制度）；2）专业技能培训（每季度2次内部分享+外部课程报销，年度额度5000元）；3）管理力培训（针对主管级以上，每半年1次）。晋升通道分为管理序列（M1-M5）和专业序列（P1-P8），每年3月和9月两次晋升评审。",
        "relevant_docs": ["培训管理制度.pdf", "职业发展手册.docx"],
        "relevance_grades": {"培训管理制度.pdf": 3, "职业发展手册.docx": 3},
        "category": "制度查询",
        "difficulty": "medium",
    },

    # ============================================================
    # 数据类 (Data Analysis) — 6 条
    # ============================================================
    {
        "id": "Q006",
        "question": "今年第一季度的销售额是多少？",
        "keywords": ["季度", "销售", "额", "Q1"],
        "ground_truth": "今年第一季度（1月-3月）公司总销售额为1850万元，同比增长12.5%。其中1月580万、2月520万、3月750万。主要增长来自互联网和金融行业客户，产品A贡献最大约占40%。",
        "relevant_docs": ["2026年Q1销售报告.xlsx", "季度经营分析.pdf"],
        "relevance_grades": {"2026年Q1销售报告.xlsx": 3, "季度经营分析.pdf": 2},
        "category": "数据分析",
        "difficulty": "medium",
    },
    {
        "id": "Q007",
        "question": "对比去年和今年的客户增长率",
        "keywords": ["增长", "客户", "同比", "去年"],
        "ground_truth": "今年客户总量较去年增长18.5%。新增客户320家，其中A级客户增长10%（新增8家），B级客户增长22%（新增45家），C级客户增长17%。客户流失率从去年的8.2%下降到6.5%。增长最快的行业是互联网（+35%）和新能源（+28%）。",
        "relevant_docs": ["客户分析报告.pdf", "年度经营报告.docx"],
        "relevance_grades": {"客户分析报告.pdf": 3, "年度经营报告.docx": 2},
        "category": "数据分析",
        "difficulty": "hard",
    },
    {
        "id": "Q014",
        "question": "上个月销售额最高的产品是哪个？",
        "keywords": ["上个月", "销售", "最高", "产品"],
        "ground_truth": "上个月销售额最高的产品是产品A，销售额为820万元，占总销售额的35%。其次是产品B（560万，24%）和产品C（420万，18%）。产品A的主要客户来自互联网和金融行业。",
        "relevant_docs": ["月度销售报表.xlsx", "产品销售分析.pdf"],
        "relevance_grades": {"月度销售报表.xlsx": 3, "产品销售分析.pdf": 3},
        "category": "数据分析",
        "difficulty": "easy",
    },
    {
        "id": "Q015",
        "question": "今年的营收目标完成情况如何？",
        "keywords": ["营收", "目标", "完成率", "KPI"],
        "ground_truth": "今年营收目标为2.5亿元，截至6月底已完成1.2亿元，完成率为48%。按季度看：Q1完成5,500万（占全年22%），Q2完成6,500万（占全年26%）。下半年需完成1.3亿元，月均需完成2,167万元。目前进度略低于预期（50%分位线），需加大销售力度。",
        "relevant_docs": ["年度经营报告.docx", "KPI考核表.xlsx"],
        "relevance_grades": {"年度经营报告.docx": 3, "KPI考核表.xlsx": 2},
        "category": "数据分析",
        "difficulty": "medium",
    },
    {
        "id": "Q016",
        "question": "哪些行业的客户贡献了最多的收入？",
        "keywords": ["行业", "客户", "收入", "贡献", "占比"],
        "ground_truth": "按行业收入贡献排名：1）互联网行业占比32%（3,840万元）；2）金融行业占比25%（3,000万元）；3）新能源行业占比18%（2,160万元）；4）制造业占比15%（1,800万元）；5）其他占比10%（1,200万元）。互联网和金融合计贡献超过57%。",
        "relevant_docs": ["客户分析报告.pdf", "行业收入分布.xlsx"],
        "relevance_grades": {"客户分析报告.pdf": 3, "行业收入分布.xlsx": 3},
        "category": "数据分析",
        "difficulty": "medium",
    },
    {
        "id": "Q017",
        "question": "员工离职率在过去一年的变化趋势是什么？",
        "keywords": ["离职率", "趋势", "变化", "流失"],
        "ground_truth": "过去一年员工离职率呈下降趋势：Q3为8.5%、Q4为7.8%、Q1为7.2%、Q2为6.5%。整体年度离职率为15.2%，低于行业平均（18%）。离职原因TOP3：薪资待遇（35%）、职业发展（28%）、工作环境（20%）。技术部门离职率最高（12%），行政部门最低（3%）。",
        "relevant_docs": ["人力资源季度报告.pdf", "员工满意度调查.xlsx"],
        "relevance_grades": {"人力资源季度报告.pdf": 3, "员工满意度调查.xlsx": 2},
        "category": "数据分析",
        "difficulty": "hard",
    },

    # ============================================================
    # OA/CRM 类 — 7 条
    # ============================================================
    {
        "id": "Q008",
        "question": "张三的请假审批通过了没有？",
        "keywords": ["张三", "请假", "审批", "通过"],
        "ground_truth": "张三最近提交了年假申请（OA-001），审批状态为已通过，审批人为部门主管李四，审批时间为2026年6月10日，请假天数为3天。",
        "relevant_docs": [],  # OA 实时查询，无静态文档
        "relevance_grades": {},
        "category": "OA查询",
        "difficulty": "easy",
    },
    {
        "id": "Q009",
        "question": "列出所有A级客户",
        "keywords": ["A级", "客户", "列表"],
        "ground_truth": "公司目前有A级客户2家：ABC科技有限公司（互联网行业，合同额500万，联系人赵总13800001001）和DEF信息技术（互联网行业，合同额450万，联系人李总13800001004）。A级客户定义为年合同额超过300万且合作年限3年以上的客户。",
        "relevant_docs": ["客户分级管理表.xlsx", "CRM客户档案.xlsx"],
        "relevance_grades": {"客户分级管理表.xlsx": 3, "CRM客户档案.xlsx": 2},
        "category": "CRM查询",
        "difficulty": "easy",
    },
    {
        "id": "Q010",
        "question": "最近一周有多少审批被驳回？原因是什么？",
        "keywords": ["驳回", "审批", "原因", "一周"],
        "ground_truth": "最近一周共有2条审批被驳回：1）OA-004采购申请（申请人赵六），驳回原因：预算超出部门限额，需重新审批；2）OA-007出差申请（申请人王五），驳回原因：出差目的地和行程说明不够详细。整体驳回率为15%。",
        "relevant_docs": [],  # OA 系统查询
        "relevance_grades": {},
        "category": "OA查询",
        "difficulty": "hard",
    },
    {
        "id": "Q018",
        "question": "ABC科技有限公司的联系人和合同信息是什么？",
        "keywords": ["ABC科技", "联系人", "合同", "信息"],
        "ground_truth": "ABC科技有限公司，联系人赵总，电话13800001001，邮箱zhao@abc-tech.com。合同编号CT-2026-001，合同额500万元，合同期限2026.1.1-2027.12.31，服务内容为智能办公系统定制开发与维护。",
        "relevant_docs": ["CRM客户档案.xlsx", "合同台账.xlsx"],
        "relevance_grades": {"CRM客户档案.xlsx": 3, "合同台账.xlsx": 3},
        "category": "CRM查询",
        "difficulty": "easy",
    },
    {
        "id": "Q019",
        "question": "上个月的出差申请都批了吗？",
        "keywords": ["出差", "审批", "上个月", "通过"],
        "ground_truth": "上个月共有15条出差申请，其中12条已通过、1条驳回（OA-008，原因：行程不合理）、2条审批中。已通过的申请涉及8个城市，平均审批时长为1.5天。",
        "relevant_docs": [],  # OA 系统查询
        "relevance_grades": {},
        "category": "OA查询",
        "difficulty": "medium",
    },
    {
        "id": "Q020",
        "question": "今年签约金额最大的三个客户是谁？",
        "keywords": ["签约", "金额", "最大", "客户", "排名"],
        "ground_truth": "今年签约金额TOP3客户：1）GHI新能源集团，合同额800万元（光伏项目）；2）JKL银行，合同额650万元（风控系统）；3）MNO制造，合同额580万元（ERP系统）。三家合计签约2,030万元，占总签约额的42%。",
        "relevant_docs": ["合同台账.xlsx", "销售业绩排名.xlsx"],
        "relevance_grades": {"合同台账.xlsx": 3, "销售业绩排名.xlsx": 3},
        "category": "CRM查询",
        "difficulty": "medium",
    },

    # ============================================================
    # 对抗/边界样本 (Edge Cases) — 5 条
    # ============================================================
    {
        "id": "Q021",
        "question": "五险一金",
        "keywords": ["五险一金", "社保", "公积金", "比例"],
        "ground_truth": "公司按照国家规定为员工缴纳五险一金：养老保险（单位16%、个人8%）、医疗保险（单位10%、个人2%）、失业保险（单位0.5%、个人0.5%）、工伤保险（单位0.4%）、生育保险（单位0.8%）、住房公积金（单位和个人各7%）。缴费基数为员工上年度月平均工资。",
        "relevant_docs": ["薪酬管理制度.pdf", "员工手册.pdf"],
        "relevance_grades": {"薪酬管理制度.pdf": 3, "员工手册.pdf": 2},
        "category": "制度查询",
        "difficulty": "easy",  # 极简查询，测试短查询鲁棒性
    },
    {
        "id": "Q022",
        "question": "不同级别的薪资范围有什么区别，晋升后薪资如何调整？",
        "keywords": ["薪资", "级别", "晋升", "调整", "涨幅"],
        "ground_truth": "公司职级薪资范围：P1-P3（初级）8K-15K，P4-P6（中级）15K-30K，P7-P8（高级）30K-50K，M1-M2（主管）25K-40K，M3-M5（经理/总监）40K-80K。晋升后薪资调整：一般晋升涨幅为10%-20%，跨级晋升涨幅为20%-35%。特别优秀的可突破上限，需VP特批。",
        "relevant_docs": ["薪酬管理制度.pdf", "绩效考核制度.docx"],
        "relevance_grades": {"薪酬管理制度.pdf": 3, "绩效考核制度.docx": 2},
        "category": "制度查询",
        "difficulty": "hard",  # 多维度复杂查询
    },
    {
        "id": "Q023",
        "question": "我想请假",
        "keywords": ["请假", "流程", "审批", "类型"],
        "ground_truth": "公司请假类型包括：年假、病假、事假、婚假（3天）、产假（98天）、陪产假（7天）、丧假（1-3天）。请假流程：登录OA系统→填写请假申请单→选择请假类型和时间→提交→等待主管审批→审批通过后生效。不同类型需提供不同证明材料。",
        "relevant_docs": ["考勤管理制度.docx", "员工手册.pdf"],
        "relevance_grades": {"考勤管理制度.docx": 3, "员工手册.pdf": 2},
        "category": "制度查询",
        "difficulty": "medium",  # 模糊查询，需要理解隐含意图
    },
    {
        "id": "Q024",
        "question": "差标",
        "keywords": ["差旅", "标准", "住宿", "交通", "餐饮"],
        "ground_truth": "差旅标准简称'差标'，包括：交通（高铁二等座/飞机经济舱，特殊情况可申请升级）、住宿（一线城市≤500元/天、其他≤350元/天）、餐饮补贴（100元/天）、市内交通（实报实销，≤100元/天）。超出标准部分需自行承担，特殊情况需提前申请。",
        "relevant_docs": ["差旅管理制度.pdf"],
        "relevance_grades": {"差旅管理制度.pdf": 3},
        "category": "制度查询",
        "difficulty": "medium",  # 缩写/行话查询
    },
    {
        "id": "Q025",
        "question": "公司对信息安全有什么规定？员工使用个人设备办公有什么要求？",
        "keywords": ["信息安全", "保密", "设备", "个人", "数据"],
        "ground_truth": "公司信息安全规定：1）所有办公电脑需安装公司指定的杀毒软件和加密软件；2）禁止使用个人邮箱传输公司内部文件；3）机密文件需加密存储，传输需使用公司VPN；4）个人设备（BYOD）需安装MDM管理软件，禁止存储A级机密数据；5）离职时需清除所有公司数据并由IT部门验证。违反信息安全规定将视情节严重程度给予警告至解除劳动合同的处分。",
        "relevant_docs": ["信息安全管理制度.pdf", "员工手册.pdf"],
        "relevance_grades": {"信息安全管理制度.pdf": 3, "员工手册.pdf": 1},
        "category": "制度查询",
        "difficulty": "hard",
    },
]


# ============================================================
# Agent 评测用例
# ============================================================

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
