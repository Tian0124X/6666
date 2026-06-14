"""FastAPI 应用入口"""

import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

# 日志配置
# 安全校验 LOG_LEVEL，防止无效值导致启动崩溃
_valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_log_level = settings.LOG_LEVEL.upper().strip() if settings.LOG_LEVEL else "INFO"
if _log_level not in _valid_log_levels:
    _log_level = "INFO"
logging.basicConfig(
    level=getattr(logging, _log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("🚀 企业智能办公助手平台启动中...")
    logger.info(f"   环境: {settings.APP_ENV}")
    logger.info(f"   模型: {settings.LLM_MODEL}")
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
