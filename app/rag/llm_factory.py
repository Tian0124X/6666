"""统一 LLM 工厂 — 消除散落的 ChatOpenAI() 构造（23处→1处）"""

from langchain_openai import ChatOpenAI
from app.config import settings


def get_llm(
    temperature: float = 0.1,
    timeout: int | None = None,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    """统一 LLM 实例工厂。

    Args:
        temperature: 生成温度（0=确定性，0.5=平衡，1.0=创造性）
        timeout: 超时秒数，默认读 settings.LLM_TIMEOUT
        max_tokens: 最大生成 token 数，None=不限制

    Returns:
        配置好的 ChatOpenAI 实例
    """
    kwargs: dict = {
        "model": settings.LLM_MODEL,
        "api_key": settings.LLM_API_KEY,
        "base_url": settings.LLM_BASE_URL,
        "temperature": temperature,
        "timeout": timeout or settings.LLM_TIMEOUT,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return ChatOpenAI(**kwargs)
