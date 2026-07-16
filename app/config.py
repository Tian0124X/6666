"""全局配置管理 — 从环境变量读取所有配置项"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _int_env(key: str, default: int) -> int:
    """安全读取整数环境变量，格式错误时回退默认值并警告"""
    val = os.getenv(key, str(default))
    try:
        return int(val)
    except (ValueError, TypeError):
        logger.warning(f"閰嶇疆 {key}={val} 涓嶆槸鏈夋晥鏁存暟锛屼娇鐢ㄩ粯璁?{default}")
        return default


class Settings:
    """全局配置单例（含启动验证）"""

    # === LLM (DeepSeek锛屽吋瀹规墍鏈?OpenAI 鎺ュ彛) ===
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", os.getenv("DASHSCOPE_API_KEY", ""))
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat")
    LLM_BASE_URL: str = os.getenv(
        "LLM_BASE_URL",
        "https://api.deepseek.com",
    )
    LLM_TIMEOUT: int = _int_env("LLM_TIMEOUT", 30)

    # === Redis ===
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # === MySQL ===
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT: int = _int_env("MYSQL_PORT", 3306)
    MYSQL_USER: str = os.getenv("MYSQL_USER", "eao_user")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "enterprise_ai_office")

    # === PostgreSQL + pgvector ===
    PG_HOST: str = os.getenv("PG_HOST", "localhost")
    PG_PORT: int = _int_env("PG_PORT", 5432)
    PG_DATABASE: str = os.getenv("PG_DATABASE", "enterprise_ai_office")
    PG_USER: str = os.getenv("PG_USER", "eao_user")
    PG_PASSWORD: str = os.getenv("PG_PASSWORD", "")

    # === 搴旂敤 ===
    APP_ENV: str = os.getenv("APP_ENV", "development")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    MAX_RETRY: int = _int_env("MAX_RETRY", 3)

    # === SSO / LDAP ===
    LDAP_ENABLED: bool = os.getenv("LDAP_ENABLED", "false").lower() == "true"
    LDAP_URL: str = os.getenv("LDAP_URL", "")
    LDAP_BASE_DN: str = os.getenv("LDAP_BASE_DN", "")
    LDAP_USER_DN_TEMPLATE: str = os.getenv("LDAP_USER_DN_TEMPLATE", "")
    OIDC_ENABLED: bool = os.getenv("OIDC_ENABLED", "false").lower() == "true"
    OIDC_ISSUER: str = os.getenv("OIDC_ISSUER", "")
    OIDC_CLIENT_ID: str = os.getenv("OIDC_CLIENT_ID", "")
    OIDC_CLIENT_SECRET: str = os.getenv("OIDC_CLIENT_SECRET", "")
    OIDC_REDIRECT_URI: str = os.getenv("OIDC_REDIRECT_URI", "http://localhost:5173/login")

    # === OA/CRM ===
    OA_API_URL: str = os.getenv("OA_API_URL", "")
    CRM_API_URL: str = os.getenv("CRM_API_URL", "")

    # === RAG 璋冧紭 ===
    RAG_SEARCH_K: int = _int_env("RAG_SEARCH_K", 20)
    RAG_RERANK_TOP_N: int = _int_env("RAG_RERANK_TOP_N", 5)
    # Cross-Encoder 默认仅离线评测；线上启用前必须通过金标集与延迟验收。
    RAG_ONLINE_RERANK: bool = os.getenv("RAG_ONLINE_RERANK", "false").lower() == "true"
    RAG_RERANK_MODEL: str = os.getenv("RAG_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
    RAG_RERANK_DEVICE: str = os.getenv("RAG_RERANK_DEVICE", "")
    RAG_RERANK_LOCAL_FILES_ONLY: bool = os.getenv("RAG_RERANK_LOCAL_FILES_ONLY", "true").lower() == "true"
    RAG_RERANK_CANDIDATE_K: int = _int_env("RAG_RERANK_CANDIDATE_K", 20)
    RAG_RERANK_MIN_CANDIDATES: int = _int_env("RAG_RERANK_MIN_CANDIDATES", 3)
    RAG_RERANK_BATCH_SIZE: int = _int_env("RAG_RERANK_BATCH_SIZE", 8)
    RAG_RERANK_TIMEOUT_MS: int = _int_env("RAG_RERANK_TIMEOUT_MS", 1200)
    RAG_RERANK_MAX_CHARS: int = _int_env("RAG_RERANK_MAX_CHARS", 1200)
    RAG_RERANK_MAX_QUERY_CHARS: int = _int_env("RAG_RERANK_MAX_QUERY_CHARS", 512)
    RAG_RERANK_MAX_LENGTH: int = _int_env("RAG_RERANK_MAX_LENGTH", 512)
    # === RAG 上下文构建 ===
    RAG_CONTEXT_MAX_TOKENS: int = _int_env("RAG_CONTEXT_MAX_TOKENS", 3000)
    RAG_CONTEXT_MIN_TOKENS_PER_SOURCE: int = _int_env("RAG_CONTEXT_MIN_TOKENS_PER_SOURCE", 180)
    RAG_CONTEXT_MAX_TOKENS_PER_SOURCE: int = _int_env("RAG_CONTEXT_MAX_TOKENS_PER_SOURCE", 900)
    RAG_CONTEXT_DOCUMENT_CAP: int = _int_env("RAG_CONTEXT_DOCUMENT_CAP", 2)
    RAG_CONTEXT_CHARS_PER_TOKEN: int = _int_env("RAG_CONTEXT_CHARS_PER_TOKEN", 2)
    # === RAG 可信生成 ===
    RAG_TRUST_MIN_EVIDENCE_CHARS: int = _int_env("RAG_TRUST_MIN_EVIDENCE_CHARS", 80)
    RAG_TRUST_MIN_QUERY_TERM_HITS: int = _int_env("RAG_TRUST_MIN_QUERY_TERM_HITS", 1)
    RAG_TRUST_MIN_CLAIM_CHARS: int = _int_env("RAG_TRUST_MIN_CLAIM_CHARS", 12)
    RAG_TRUST_REGENERATION_ENABLED: bool = os.getenv("RAG_TRUST_REGENERATION_ENABLED", "true").lower() == "true"
    # === RAG 过程追踪 ===
    RAG_TRACE_ENABLED: bool = os.getenv("RAG_TRACE_ENABLED", "true").lower() == "true"
    RAG_EMBEDDING_MODEL: str = os.getenv("RAG_EMBEDDING_MODEL", "BAAI/bge-m3")
    RAG_EMBEDDING_DIMENSION: int = _int_env("RAG_EMBEDDING_DIMENSION", 1024)
    # === RAG QueryPlan 与受控召回 ===
    RAG_QUERY_PLAN_ENABLED: bool = os.getenv("RAG_QUERY_PLAN_ENABLED", "true").lower() == "true"
    RAG_QUERY_PLAN_VARIANT_LIMIT: int = _int_env("RAG_QUERY_PLAN_VARIANT_LIMIT", 2)
    RAG_QUERY_PLAN_MIN_CANDIDATES: int = _int_env("RAG_QUERY_PLAN_MIN_CANDIDATES", 3)
    RAG_QUERY_PLAN_MIN_TERM_HITS: int = _int_env("RAG_QUERY_PLAN_MIN_TERM_HITS", 4)
    RAG_QUERY_PLAN_DOCUMENT_CAP: int = _int_env("RAG_QUERY_PLAN_DOCUMENT_CAP", 2)
    # === RAG 反馈运营 ===
    RAG_FEEDBACK_SLA_HOURS: int = _int_env("RAG_FEEDBACK_SLA_HOURS", 72)
    # 当前答案金标 P95 为 2810.7ms，默认以 3000ms 作为运行态总耗时预警线。
    RAG_TOTAL_LATENCY_ALERT_P95_MS: int = _int_env("RAG_TOTAL_LATENCY_ALERT_P95_MS", 3000)
    RAG_LATENCY_ALERT_MIN_SAMPLES: int = _int_env("RAG_LATENCY_ALERT_MIN_SAMPLES", 20)
    # === RAG 记忆边界 ===
    RAG_MEMORY_RECENT_TURNS: int = _int_env("RAG_MEMORY_RECENT_TURNS", 6)
    RAG_MEMORY_SUMMARY_TRIGGER_TURNS: int = _int_env("RAG_MEMORY_SUMMARY_TRIGGER_TURNS", 8)
    RAG_MEMORY_SUMMARY_SOURCE_TURNS: int = _int_env("RAG_MEMORY_SUMMARY_SOURCE_TURNS", 16)
    RAG_MEMORY_PREFERENCE_LIMIT: int = _int_env("RAG_MEMORY_PREFERENCE_LIMIT", 5)
    # === MinerU PDF 增强解析 ===
    PDF_PARSER: str = os.getenv("PDF_PARSER", "auto")
    MINERU_OCR: bool = os.getenv("MINERU_OCR", "false").lower() == "true"
    MINERU_BACKEND: str = os.getenv("MINERU_BACKEND", "pipeline")  # pipeline | vlm-engine | hybrid-engine

    def validate(self) -> list[str]:
        """启动时验证关键配置。返回警告列表。"""
        warnings = []
        if not self.LLM_API_KEY or self.LLM_API_KEY.startswith("sk-your-"):
            warnings.append(
                "LLM_API_KEY 未配置或为占位符，请设置 .env 中的 LLM_API_KEY。"
                "LLM 调用将使用回退模式（规则引擎/Mock）。"
            )
        if not self.MYSQL_PASSWORD:
            warnings.append("MYSQL_PASSWORD 为空，数据库连接可能失败。")
        return warnings

    @property
    def is_llm_available(self) -> bool:
        return bool(self.LLM_API_KEY) and not self.LLM_API_KEY.startswith("sk-your-")

    @property
    def mysql_url(self) -> str:
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            f"?charset=utf8mb4"
        )

settings = Settings()

