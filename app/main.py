"""
FastAPI 应用入口 — 含令牌桶速率限制中间件
"""

import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

# 日志配置
_valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_log_level = settings.LOG_LEVEL.upper().strip() if settings.LOG_LEVEL else "INFO"
if _log_level not in _valid_log_levels:
    _log_level = "INFO"
logging.basicConfig(
    level=getattr(logging, _log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ====== 令牌桶限流器 ======

class TokenBucket:
    """简单的令牌桶限流：按 IP 限制请求速率"""

    def __init__(self, rate: int = 30, burst: int = 60):
        """
        rate: 每秒补充令牌数 (默认 30 req/s)
        burst: 桶容量 (默认 60, 允许突发)
        """
        self.rate = rate
        self.burst = burst
        self.buckets: dict[str, tuple[float, float]] = {}  # ip → (tokens, last_update)

    def consume(self, key: str) -> bool:
        """尝试消费 1 个令牌。返回 True=允许, False=限流"""
        now = time.time()
        tokens, last = self.buckets.get(key, (self.burst, now))
        # 补充令牌
        tokens = min(self.burst, tokens + (now - last) * self.rate)
        self.buckets[key] = (tokens, now)

        if tokens >= 1:
            self.buckets[key] = (tokens - 1, now)
            return True
        return False

_token_bucket = TokenBucket(rate=30, burst=60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("🚀 企业智能办公助手平台启动中...")
    logger.info(f"   环境: {settings.APP_ENV}")
    logger.info(f"   模型: {settings.LLM_MODEL}")
    logger.info(f"   限流: 30 req/s (突发 60)")
    yield
    logger.info("👋 应用关闭")


app = FastAPI(
    title="企业智能办公助手平台 API",
    description="基于 LangGraph + LangChain 的 Multi-Agent 智能办公平台",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 速率限制中间件
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """令牌桶限流 — 按客户端 IP"""
    # 跳过静态资源 & 健康检查
    path = request.url.path
    if path in ("/api/health", "/docs", "/redoc", "/openapi.json"):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    if not _token_bucket.consume(client_ip):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后重试")

    return await call_next(request)


# 请求日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    logger.info(
        f"{request.method} {request.url.path} → {response.status_code} ({duration:.2f}s)"
    )
    return response


# ========== 注册路由 ==========
from app.api import chat, knowledge, tools, monitoring, auth, eval

app.include_router(chat.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api/knowledge")
app.include_router(tools.router, prefix="/api/tools")
app.include_router(monitoring.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(eval.router, prefix="/api")


# ========== 健康检查 ==========
@app.get("/api/health", tags=["系统"])
async def health_check():
    return {
        "status": "ok",
        "version": "1.0.0",
        "llm_model": settings.LLM_MODEL,
    }


@app.get("/api/info", tags=["系统"])
async def system_info():
    """系统信息（含服务连接状态）"""
    info = {
        "version": "1.0.0",
        "llm_model": settings.LLM_MODEL,
        "services": {},
    }

    # 启动时验证配置
    config_warnings = settings.validate()
    for w in config_warnings:
        logger.warning(f"⚠️ 配置警告: {w}")

    # Redis
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        r.ping()
        info["services"]["redis"] = "connected"
        r.close()
    except Exception as e:
        info["services"]["redis"] = f"unavailable ({e})"

    # ChromaDB (使用实际客户端连接而非 HTTP heartbeat)
    try:
        from app.rag.store import get_vector_store
        store = get_vector_store()
        count = store._collection.count()
        info["services"]["chromadb"] = f"connected ({count} chunks)"
    except Exception as e:
        info["services"]["chromadb"] = f"unavailable ({e})"

    return info
