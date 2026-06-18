"""语义记忆 — 跨会话用户事实提取与检索

参考 Mem0 的 add()/search() 模式，用 MySQL 存储，后续可扩展到 pgvector。

每轮对话结束后异步提取用户事实 (偏好/身份/上下文)。
每次对话开始时注入 top 5 相关事实到 system prompt。
"""

import json
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

FACT_EXTRACTION_PROMPT = """从以下对话中提取关于用户的**新事实或偏好**。
只提取明确的信息，不要猜测。输出 JSON 数组 (不含 markdown):

[
  {"fact": "用户偏好简短回答", "category": "preference"},
  {"fact": "用户负责华东区销售", "category": "fact"},
  {"fact": "用户上次讨论过 Q2 预算", "category": "context"}
]

分类: preference(偏好), fact(身份/事实), context(上下文关联), skill(技能)

对话:
{conversation}

只输出 JSON 数组，无其他文字。如果没有新事实输出 []。"""


def _mysql_session():
    try:
        from app.models.database import get_session
        return get_session()
    except Exception:
        return None


def extract_facts(user_id: str, messages: list) -> list[dict]:
    """从一轮对话中异步提取用户事实。

    每轮用户+助手对话后调用。返回提取到的事实列表。
    """
    if not settings.is_llm_available or len(messages) < 2:
        return []

    # 只取最近 6 条消息
    recent = messages[-6:]
    conversation_text = "\n".join(
        f"[{m.role}]: {m.content[:200]}" for m in recent
    )

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=0, timeout=10,
        )
        response = llm.invoke([
            SystemMessage(content="你从对话中提取用户事实。只输出 JSON 数组。"),
            HumanMessage(content=FACT_EXTRACTION_PROMPT.format(conversation=conversation_text)),
        ])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]

        facts = json.loads(raw)
        if not isinstance(facts, list):
            return []

        # 存储到 MySQL
        stored = []
        for f in facts:
            fact_text = f.get("fact", "").strip()
            if not fact_text or len(fact_text) < 3:
                continue
            category = f.get("category", "general")
            _save_fact(user_id, fact_text, category)
            stored.append({"fact": fact_text, "category": category})

        if stored:
            logger.info(f"提取 {len(stored)} 条用户事实: user={user_id}")
        return stored
    except Exception as e:
        logger.debug(f"事实提取跳过: {e}")
        return []


def _save_fact(user_id: str, fact_text: str, category: str = "general"):
    """保存一条事实 (去重: 完全相同跳过)"""
    sess = _mysql_session()
    if sess is None:
        return
    try:
        from sqlalchemy import text as sa_text
        # 检查重复
        existing = sess.execute(
            sa_text(
                "SELECT id FROM user_facts WHERE user_id = :uid AND fact_text = :ft LIMIT 1"
            ),
            {"uid": user_id, "ft": fact_text},
        ).fetchone()
        if existing:
            # 更新访问计数
            sess.execute(
                sa_text(
                    "UPDATE user_facts SET last_accessed_at = NOW(), access_count = access_count + 1 WHERE id = :id"
                ),
                {"id": existing[0]},
            )
        else:
            sess.execute(
                sa_text(
                    "INSERT INTO user_facts (user_id, fact_text, category) VALUES (:uid, :ft, :cat)"
                ),
                {"uid": user_id, "ft": fact_text, "cat": category},
            )
        sess.commit()
    except Exception as e:
        logger.warning(f"保存事实失败: {e}")
    finally:
        sess.close()


def get_user_facts(user_id: str, category: str = None, limit: int = 10) -> list[dict]:
    """获取用户的事实列表。可按 category 过滤。"""
    sess = _mysql_session()
    if sess is None:
        return []
    try:
        from sqlalchemy import text as sa_text
        if category:
            rows = sess.execute(
                sa_text(
                    "SELECT fact_text, category, confidence, access_count FROM user_facts "
                    "WHERE user_id = :uid AND category = :cat "
                    "ORDER BY access_count DESC, created_at DESC LIMIT :lim"
                ),
                {"uid": user_id, "cat": category, "lim": limit},
            ).fetchall()
        else:
            rows = sess.execute(
                sa_text(
                    "SELECT fact_text, category, confidence, access_count FROM user_facts "
                    "WHERE user_id = :uid "
                    "ORDER BY access_count DESC, created_at DESC LIMIT :lim"
                ),
                {"uid": user_id, "lim": limit},
            ).fetchall()

        return [
            {"fact": r[0], "category": r[1], "confidence": r[2], "access_count": r[3]}
            for r in rows
        ]
    except Exception:
        return []
    finally:
        sess.close()


def inject_facts_to_prompt(user_id: str, existing_facts: list[dict] = None) -> str:
    """生成用户事实注入文本，附加到 system prompt 开头。

    格式: "[用户画像] 偏好xxx; 身份: xxx; 上下文: xxx"
    """
    if existing_facts is None:
        existing_facts = get_user_facts(user_id, limit=5)

    if not existing_facts:
        return ""

    prefs = [f["fact"] for f in existing_facts if f["category"] == "preference"]
    facts = [f["fact"] for f in existing_facts if f["category"] == "fact"]
    ctx = [f["fact"] for f in existing_facts if f["category"] == "context"]

    parts = []
    if prefs:
        parts.append(f"偏好: {'; '.join(prefs)}")
    if facts:
        parts.append(f"信息: {'; '.join(facts)}")
    if ctx:
        parts.append(f"上下文: {'; '.join(ctx)}")

    if parts:
        return f"[用户画像] {' | '.join(parts)}"
    return ""
