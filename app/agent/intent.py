"""
统一意图识别器 — 智能办公助手的唯一路由入口

设计原则:
1. 规则优先 (>80%命中, 0延迟) → LLM兜底 (歧义消息)
2. 单点维护: 所有路由规则集中在此, router/multi_agent/fallback 统一调用
3. 上下文感知: 考虑上传文件、对话历史、消息长度

意图分类体系 (8类):
  greeting      — 问候/感谢/告别/功能询问
  data_analysis — 有上传文件 + 数据问题
  data_report   — 生成/导出报告
  knowledge_qa  — 公司制度/文档/FAQ
  oa_query      — 审批/请假/报销/出差
  crm_query     — 客户/CRM
  general_chat  — 以上都不匹配
  multi_domain  — 跨领域复杂问题 (LLM判断)
"""

from __future__ import annotations

import re
import json
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


class Intent(str, Enum):
    GREETING = "greeting"
    DATA_ANALYSIS = "data_analysis"
    DATA_REPORT = "data_report"
    KNOWLEDGE_QA = "knowledge_qa"
    OA_QUERY = "oa_query"
    CRM_QUERY = "crm_query"
    GENERAL_CHAT = "general_chat"
    MULTI_DOMAIN = "multi_domain"


@dataclass
class IntentResult:
    primary: Intent
    confidence: float  # 0.0 ~ 1.0
    sub_intents: list[Intent] = field(default_factory=list)
    reason: str = ""


# ============================================================
# 规则引擎 — 从3套旧规则合并+去重+补全
# 来源: router.py STRONG_COMPLEX/SIMPLE, multi_agent.py KEYWORD_AGENT_MAP,
#        fallback.py RULE_TABLE, chat.py 快速/兜底通道
# ============================================================

# 格式: (regex_pattern, Intent, confidence, priority)
# priority 越小越优先匹配
RuleEntry = tuple[str, Intent, float, int]

RULES: list[RuleEntry] = [
    # ═══ greeting (priority=0, 最高优先) ═══
    (r"^(你好|hi|hello|嗨|早上好|下午好|晚上好|晚安)[\s!！。.,，]*$",
     Intent.GREETING, 1.0, 0),
    (r"^(再见|bye|拜拜|回头见)[\s!！。.,，]*$",
     Intent.GREETING, 1.0, 0),
    (r"^(谢谢|感谢|thank|多谢|辛苦了|麻烦你了)[\s!！。.,，]*$",
     Intent.GREETING, 1.0, 0),
    (r"^(你是谁|能做什么|帮助|help|功能|介绍一下|你会什么|你能干什么)[\s!！。.,，]*$",
     Intent.GREETING, 1.0, 0),

    # ═══ data_report (priority=1, 比 data_analysis 更具体) ═══
    (r"(生成|导出|下载|制作|创建|写).*(报告|报表|word|doc|文档|分析报告)",
     Intent.DATA_REPORT, 0.95, 1),
    (r"(报告|报表|分析报告).*(生成|导出|下载|制作|创建)",
     Intent.DATA_REPORT, 0.95, 1),
    (r"导出.*(报表|excel|pdf)",
     Intent.DATA_REPORT, 0.90, 1),

    # ═══ data_analysis — 数据关键词 (priority=2) ═══
    # (文件标记逻辑已移至 classify_intent() 主函数中处理)
    (r"(分析|统计|趋势|排名|占比|汇总|对比|图表|最高|最低|平均|增长|下降|分布|变化|筛选|排序|过滤|分类|分组)",
     Intent.DATA_ANALYSIS, 0.55, 3),

    # ═══ oa_query (priority=2) ═══
    (r"(审批|OA|请假|报销|出差|加班|申请|工时|考勤打卡)",
     Intent.OA_QUERY, 0.90, 2),

    # ═══ crm_query (priority=2) ═══
    (r"(客户|CRM|行业|联系|线索|商机|客户信息|客户列表)",
     Intent.CRM_QUERY, 0.90, 2),

    # ═══ knowledge_qa — 强信号 (priority=2) ═══
    (r"(制度|文档|手册|规定|政策|FAQ|流程|指南|年假|福利|考勤制度|公司规章)",
     Intent.KNOWLEDGE_QA, 0.90, 2),
    # knowledge_qa — 弱信号 (疑问句式)
    (r"(怎么|如何|为什么|什么是|能不能|可以.*吗|有没有|在哪里|什么时候|谁负责)",
     Intent.KNOWLEDGE_QA, 0.55, 3),

    # ═══ data_analysis — 无文件, 数据关键词 (priority=3, 低置信度) ═══
    (r"(分析.*数据|数据.*分析|统计分析|趋势分析|对比分析)",
     Intent.DATA_ANALYSIS, 0.70, 3),
    (r"(分析|统计|图表|报表|数据|趋势|汇总|对比|排名|占比)",
     Intent.DATA_ANALYSIS, 0.45, 3),

    # ═══ multi_domain — 跨领域组合 (priority=2, LLM 确认) ═══
    (r".*(分析|数据|报表).*(审批|OA|请假|客户|CRM|搜索|查询).*",
     Intent.MULTI_DOMAIN, 0.55, 2),
    (r".*(审批|OA|请假|客户|CRM).*(分析|数据|报表|统计).*",
     Intent.MULTI_DOMAIN, 0.55, 2),
]

# 短消息 + 无文件 → greeting / general_chat
SHORT_MESSAGE_PATTERN = re.compile(r"^.{1,4}$")

# 数据类关键词 (用于兜底: 无文件但有数据意图时导向示例数据或提示上传)
DATA_KEYWORDS_RE = re.compile(
    r"(分析|统计|图表|报表|数据|趋势|汇总|对比|排名|占比|最高|最低|平均)"
)


# ============================================================
# LLM 兜底 — 仅用于规则无法确定的歧义消息
# ============================================================

INTENT_LLM_PROMPT = """判断用户消息的意图。可选意图:
- greeting: 问候、感谢、告别、询问助手功能
- data_analysis: 分析数据、统计、图表、趋势
- data_report: 生成/导出报告
- knowledge_qa: 询问公司制度、文档、规定、操作方法
- oa_query: 审批、请假、报销、出差等OA事务
- crm_query: 客户信息、CRM查询
- general_chat: 一般闲聊、无法归类的问题
- multi_domain: 跨多个领域(如同时涉及数据分析和OA)

用户消息: {message}

只输出JSON: {{"primary":"...","confidence":0.0~1.0,"reason":"..."}}"""


def _llm_classify(message: str) -> IntentResult:
    """LLM 意图分类 (仅用于规则无法判定的歧义消息)"""
    if not settings.is_llm_available:
        # LLM 不可用 → 保守路由到 general_chat (Agent 全工具集兜底)
        return IntentResult(Intent.GENERAL_CHAT, 0.4, reason="LLM不可用, 兜底general_chat")

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage

        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=0, timeout=10, max_tokens=200,
        )
        raw = llm.invoke([
            HumanMessage(content=INTENT_LLM_PROMPT.format(message=message)),
        ])
        text = raw.content.strip() if hasattr(raw, 'content') else str(raw).strip()

        # 提取 JSON
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            data = json.loads(m.group(0))
            primary = Intent(data.get("primary", "general_chat"))
            confidence = float(data.get("confidence", 0.5))
            return IntentResult(
                primary=primary,
                confidence=min(max(confidence, 0.0), 1.0),
                reason=data.get("reason", "LLM判断"),
            )
    except Exception as e:
        logger.warning(f"LLM 意图分类失败: {e}")

    return IntentResult(Intent.GENERAL_CHAT, 0.4, reason="LLM失败, 兜底general_chat")


# ============================================================
# 主入口
# ============================================================

def classify_intent(
    message: str,
    has_file: bool = False,
    history: list | None = None,
) -> IntentResult:
    """
    统一意图识别入口。

    Args:
        message: 用户消息 (可能包含文件标记)
        has_file: 当前会话是否有已上传的数据文件
        history: 最近对话历史 (可选, 用于上下文感知)

    Returns:
        IntentResult with primary intent, confidence, sub_intents
    """
    # 清理消息 (去除文件标记，保留用户真实问题)
    clean = re.sub(r'\[已上传数据文件:\s*[^\]]+\]\s*', '', message)
    clean = clean.replace('用户问题:', '').strip()

    # 0. 优先检测 greeting — 在清洗后的消息上检测，不受文件标记干扰
    if is_simple_greeting(clean):
        return IntentResult(Intent.GREETING, 0.85, reason="问候检测(clean)")
    # 极短消息(≤2字)且非数据问题 → greeting
    if len(clean) <= 2 and not has_data_question(clean):
        return IntentResult(Intent.GREETING, 0.80, reason="极短消息(clean)")

    # === 核心逻辑: 有文件 ≠ 数据分析 ===
    # 先判断清洗后的问题本身是什么意图。
    # 文件只是"如果用户想分析数据，有数据可用"的上下文，
    # 不应改变用户的真实意图。

    # 检查清洗后的问题是否包含数据相关提问
    clean_has_data_q = has_data_question(clean)

    if has_file and clean_has_data_q:
        # 有文件 + 数据问题 → 数据分析（高置信度）
        # 但如果是"生成报告"类，提升为 data_report
        if re.search(r"(生成|导出|下载|制作|创建|写).*(报告|报表|word|doc|文档)", clean):
            reason_text = "文件+报告关键词 → data_report"
            return IntentResult(Intent.DATA_REPORT, 0.95, reason=reason_text)
        reason_text = "文件+数据关键词 → data_analysis"
        return IntentResult(Intent.DATA_ANALYSIS, 0.92, reason=reason_text)

    if has_file and not clean_has_data_q:
        # 有文件但没有数据问题 → 文件不应改变意图
        # 走下面的正常规则匹配（文件标记已从 clean 中移除）
        logger.info(f"有文件但问题无数据关键词, 走普通意图: {clean[:60]}")
        # 继续往下，用 clean 消息做规则匹配

    # 1. 规则匹配 (用 clean 消息匹配，不受文件标记干扰)
    target = clean if has_file else message
    hits: list[tuple[int, float, Intent, str]] = []
    for pattern, intent, conf, pri in RULES:
        # 跳过文件标记相关的规则（已在上面处理）
        if r"\[已上传数据文件" in pattern:
            continue
        if re.search(pattern, target):
            hits.append((pri, -conf, intent, f"规则匹配: {pattern[:50]}"))

    if hits:
        hits.sort(key=lambda x: (x[0], x[1]))
        _, _, primary, reason = hits[0]
        conf = -hits[0][1]
    else:
        primary, conf, reason = Intent.GENERAL_CHAT, 0.35, "无规则命中, 兜底general_chat"

    # 2. 如果无规则命中且有文件 → 提示用户有数据可用但不要强制分析
    if primary == Intent.GENERAL_CHAT and has_file and conf < 0.5:
        # 有文件但问题不相关 → 仍是 general_chat
        # 但 confidence 稍高因为用户可能有隐含意图
        conf = 0.45

    result = IntentResult(
        primary=primary,
        confidence=round(conf, 2),
        sub_intents=[],
        reason=reason,
    )

    # 3. LLM 兜底: 规则置信度 < 0.5 时调 LLM
    if result.confidence < 0.5 and settings.is_llm_available:
        logger.info(f"规则低置信度({result.confidence}), 调LLM: {clean[:60]}")
        llm_result = _llm_classify(clean)

        # LLM 比规则更确定时，以 LLM 为准
        if llm_result.confidence > result.confidence:
            result = llm_result
            result.reason = f"LLM修正({llm_result.reason})"

    logger.info(
        f"意图: {result.primary.value} conf={result.confidence} "
        f"| {clean[:60]}..."
    )
    return result


# ============================================================
# 便捷函数 — 供 router.py / multi_agent.py / fallback.py 复用
# ============================================================

def is_simple_greeting(message: str) -> bool:
    """快速判断: 是否为简单问候 (0延迟, 纯规则)"""
    return bool(re.search(
        r"^(你好|hi|hello|嗨|早上好|下午好|晚上好|晚安|再见|bye|拜拜|谢谢|感谢|thank|你是谁|能做什么|帮助|help|功能)",
        message.strip()
    ))


def extract_file_path(message: str) -> str | None:
    """从消息中提取已上传文件路径"""
    m = re.search(r"\[已上传数据文件:\s*([^\]]+)\]", message)
    return m.group(1).strip() if m else None


def has_data_question(message: str) -> bool:
    """快速判断: 是否包含数据分析相关提问"""
    clean = re.sub(r'\[已上传数据文件:\s*[^\]]+\]\s*', '', message)
    clean = clean.replace('用户问题:', '').strip()
    return bool(DATA_KEYWORDS_RE.search(clean))
