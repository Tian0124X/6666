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
    # CPU Cross-Encoder 会造成二十秒级延迟，默认只允许离线评测使用。
    RAG_ONLINE_RERANK: bool = os.getenv("RAG_ONLINE_RERANK", "false").lower() == "true"
    RAG_EMBEDDING_MODEL: str = os.getenv("RAG_EMBEDDING_MODEL", "BAAI/bge-m3")
    RAG_EMBEDDING_DIMENSION: int = _int_env("RAG_EMBEDDING_DIMENSION", 1024)
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

