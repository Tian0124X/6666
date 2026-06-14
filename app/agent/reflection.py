"""
反思重试模块 — 2026 最佳实践：状态级重试 + 错误分类 + 指数退避 + 熔断

参考: deep-research-agent 的 Circuit Breaker 模式
"""

import logging
import asyncio
from typing import Optional
from enum import Enum
from langchain_openai import ChatOpenAI
from app.config import settings

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    TIMEOUT = "timeout"
    NETWORK = "network"
    TOOL_ERROR = "tool_error"
    PARAM_ERROR = "param_error"
    PERMISSION = "permission"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


RETRY_MATRIX = {
    ErrorCategory.TIMEOUT:     {"can_retry": True,  "max_retry": 3, "backoff": True},
    ErrorCategory.NETWORK:     {"can_retry": True,  "max_retry": 3, "backoff": True},
    ErrorCategory.TOOL_ERROR:  {"can_retry": True,  "max_retry": 2, "backoff": False},
    ErrorCategory.PARAM_ERROR: {"can_retry": True,  "max_retry": 2, "backoff": False},
    ErrorCategory.PERMISSION:  {"can_retry": False, "max_retry": 0, "backoff": False},
    ErrorCategory.NOT_FOUND:   {"can_retry": False, "max_retry": 0, "backoff": False},
    ErrorCategory.UNKNOWN:     {"can_retry": True,  "max_retry": 1, "backoff": False},
}


def categorize_error(error: Exception) -> ErrorCategory:
    msg = str(error).lower()
    if "timeout" in msg or "timed out" in msg:
        return ErrorCategory.TIMEOUT
    if any(kw in msg for kw in ["connection", "network", "refused", "reset"]):
        return ErrorCategory.NETWORK
    if "permission" in msg or "denied" in msg or "unauthorized" in msg:
        return ErrorCategory.PERMISSION
    if "not found" in msg or "no such file" in msg or "does not exist" in msg:
        return ErrorCategory.NOT_FOUND
    if any(kw in msg for kw in ["param", "argument", "invalid", "type error", "keyerror"]):
        return ErrorCategory.PARAM_ERROR
    return ErrorCategory.TOOL_ERROR


class ReflectionHandler:
    """状态级反思重试处理器"""

    def __init__(self, max_total_retries: int = 3):
        self.max_total_retries = max_total_retries
        self._task_retries: dict[str, int] = {}

    async def can_retry(self, task_id: str, error: Exception) -> bool:
        """判断是否可重试（含熔断检查）。异步执行，不阻塞事件循环。"""
        count = self._task_retries.get(task_id, 0)
        if count >= self.max_total_retries:
            logger.warning(f"任务 {task_id} 已达全局熔断上限 ({self.max_total_retries})")
            return False

        category = categorize_error(error)
        matrix = RETRY_MATRIX[category]

        if category == ErrorCategory.PERMISSION or category == ErrorCategory.NOT_FOUND:
            logger.info(f"错误类型 {category.value} 不可重试")
            return False

        if matrix["backoff"]:
            wait = 2 ** count
            logger.info(f"指数退避 {wait}s (第 {count+1} 次重试)")
            await asyncio.sleep(wait)

        return True

    def record_attempt(self, task_id: str):
        self._task_retries[task_id] = self._task_retries.get(task_id, 0) + 1

    async def analyze_and_fix(
        self, task_description: str, error_message: str, params: dict,
    ) -> Optional[dict]:
        """LLM 分析错误，尝试生成修正参数（异步，不阻塞事件循环）"""
        if not settings.LLM_API_KEY or settings.LLM_API_KEY.startswith("sk-your-"):
            return None

        try:
            llm = ChatOpenAI(
                model=settings.LLM_MODEL,
                api_key=settings.LLM_API_KEY,
                base_url=settings.LLM_BASE_URL,
                temperature=0, timeout=15,
            )

            prompt = f"""任务执行失败，分析错误并修正参数。
任务: {task_description}
错误: {error_message}
原参数: {params}

如果可以修正参数重试，输出修正后的 JSON 参数；否则输出 "NO_RETRY"。
只输出 JSON 或 NO_RETRY。"""

            result = (await llm.ainvoke(prompt)).content.strip()
            if "NO_RETRY" in result:
                return None
            import json
            return json.loads(result)
        except Exception:
            return None
