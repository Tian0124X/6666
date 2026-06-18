"""情景记忆摘要管线 — 参考 Hindsight / CrewAI 的 N 轮摘要策略

触发条件:
- 对话轮次 >= SUMMARIZE_EVERY=12 → LLM 生成中间摘要
- 会话结束/切换时 → 异步生成最终摘要

存储: Redis HSET + MySQL conversation_summaries 表
"""

import json
import logging
from datetime import datetime
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

SUMMARIZE_EVERY = 12  # 每 12 轮触发摘要

# ====== 数据模型 ======

SUMMARY_SCHEMA = {
    "session_id": "",
    "user_id": "",
    "summary": "",         # ≤200 字简短叙述
    "key_topics": [],       # ["主题1", "主题2"]
    "decisions": [],        # ["决定1"]
    "entities_mentioned": [],  # ["实体1", "实体2"]
    "turn_count": 0,
    "is_final": False,
    "timestamp": "",
}


def _redis_client():
    try:
        from app.memory.store import _get_redis
        return _get_redis()
    except Exception:
        return None


def _mysql_session():
    try:
        from app.models.database import get_session
        return get_session()
    except Exception:
        return None


def get_summary(session_id: str, user_id: str) -> Optional[dict]:
    """读取已有摘要 (Redis 优先)"""
    redis = _redis_client()
    if redis:
        try:
            raw = redis.hget(f"summary:{user_id}:{session_id}", "latest")
            if raw:
                return json.loads(raw)
        except Exception:
            pass

    sess = _mysql_session()
    if sess:
        try:
            from sqlalchemy import text as sa_text
            row = sess.execute(
                sa_text(
                    "SELECT summary_json FROM conversation_summaries "
                    "WHERE session_id = :sid AND user_id = :uid "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"sid": session_id, "uid": user_id},
            ).fetchone()
            if row:
                return json.loads(row[0])
        except Exception:
            pass
        finally:
            sess.close()

    return None


def save_summary(summary_data: dict):
    """保存摘要到 Redis + MySQL"""
    sid = summary_data["session_id"]
    uid = summary_data["user_id"]

    redis = _redis_client()
    if redis:
        try:
            redis.hset(
                f"summary:{uid}:{sid}",
                "latest",
                json.dumps(summary_data, ensure_ascii=False),
            )
        except Exception as e:
            logger.warning(f"Redis 写摘要失败: {e}")

    sess = _mysql_session()
    if sess:
        try:
            from sqlalchemy import text as sa_text
            sess.execute(
                sa_text(
                    """INSERT INTO conversation_summaries
                       (session_id, user_id, summary_json, is_final, created_at)
                       VALUES (:sid, :uid, :json, :final, NOW())
                       ON DUPLICATE KEY UPDATE summary_json = VALUES(summary_json),
                                               is_final = VALUES(is_final)"""
                ),
                {
                    "sid": sid, "uid": uid,
                    "json": json.dumps(summary_data, ensure_ascii=False),
                    "final": 1 if summary_data.get("is_final") else 0,
                },
            )
            sess.commit()
        except Exception as e:
            logger.warning(f"MySQL 写摘要失败: {e}")
        finally:
            sess.close()


def should_summarize(turn_count: int) -> bool:
    """判断当前是否应触发摘要"""
    return turn_count > 0 and turn_count % SUMMARIZE_EVERY == 0


def build_summary_prompt(messages: list, existing_summary: Optional[dict] = None) -> str:
    """构建摘要 LLM prompt"""
    existing_text = ""
    if existing_summary:
        existing_text = f"已有摘要: {existing_summary.get('summary', '')}\n已知主题: {', '.join(existing_summary.get('key_topics', []))}\n"

    # 取最近 20 轮消息
    conversation_text = "\n".join(
        f"[{m.role}]: {m.content[:300]}" for m in messages[-40:]
    )

    return f"""请总结以下对话片段，输出 JSON (不含 markdown 代码块):

{existing_text}
最近对话:
{conversation_text}

输出格式:
{{
  "summary": "简短叙述 (≤200 字)",
  "key_topics": ["主题1", "主题2"],
  "decisions": ["决定1"],
  "entities_mentioned": ["实体1"]
}}
只输出 JSON。"""


def generate_summary(
    session_id: str, user_id: str, messages: list,
    is_final: bool = False,
) -> Optional[dict]:
    """调用 LLM 生成摘要。失败返回 None。"""
    if not settings.is_llm_available or len(messages) < 4:
        return None

    existing = get_summary(session_id, user_id)
    prompt = build_summary_prompt(messages, existing)

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=0, timeout=15,
        )
        response = llm.invoke([
            SystemMessage(content="你是对话摘要专家。只输出 JSON，不含其他文字。"),
            HumanMessage(content=prompt),
        ])
        raw = response.content.strip()
        # 清理可能的 markdown 代码块标记
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]

        data = json.loads(raw)
        summary = {
            **SUMMARY_SCHEMA,
            "session_id": session_id,
            "user_id": user_id,
            "summary": data.get("summary", "")[:200],
            "key_topics": data.get("key_topics", []),
            "decisions": data.get("decisions", []),
            "entities_mentioned": data.get("entities_mentioned", []),
            "turn_count": len(messages) // 2,
            "is_final": is_final,
            "timestamp": datetime.now().isoformat(),
        }
        save_summary(summary)
        logger.info(f"摘要已生成: session={session_id[:12]}... turns={summary['turn_count']} final={is_final}")
        return summary
    except Exception as e:
        logger.warning(f"摘要生成失败: {e}")
        return None


def generate_final_summary(session_id: str, user_id: str, messages: list) -> Optional[dict]:
    """会话结束时的最终摘要。is_final=True。"""
    return generate_summary(session_id, user_id, messages, is_final=True)


def inject_summary_to_context(summary: dict, context_lines: list) -> list:
    """将结构化摘要注入到上下文开头"""
    if not summary:
        return context_lines

    parts = [
        f"[对话摘要] {summary.get('summary', '')}",
    ]
    topics = summary.get("key_topics", [])
    if topics:
        parts.append(f"讨论主题: {', '.join(topics)}")
    decisions = summary.get("decisions", [])
    if decisions:
        parts.append(f"用户决定: {', '.join(decisions)}")

    return ["\n".join(parts)] + context_lines
