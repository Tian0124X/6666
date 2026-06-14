"""企业智能办公助手平台 — FastAPI 入口（唯一 main.py）

启动:
  python main.py              → http://localhost:8000
  uvicorn main:app --reload   → 开发模式热重载
  PyCharm: Run main.py        → 自动识别 FastAPI app
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

# ====== 日志 ======
_valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_log_level = settings.LOG_LEVEL.upper().strip() if settings.LOG_LEVEL else "INFO"
if _log_level not in _valid_log_levels:
    _log_level = "INFO"
logging.basicConfig(
    level=getattr(logging, _log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ====== 令牌桶限流 ======

class TokenBucket:
    """令牌桶限流：按 IP 限制请求速率"""

    def __init__(self, rate: int = 30, burst: int = 60):
        self.rate = rate
        self.burst = burst
        self.buckets: dict[str, tuple[float, float]] = {}

    def consume(self, key: str) -> bool:
        now = time.time()
        tokens, last = self.buckets.get(key, (self.burst, now))
        tokens = min(self.burst, tokens + (now - last) * self.rate)
        self.buckets[key] = (tokens, now)
        if tokens >= 1:
            self.buckets[key] = (tokens - 1, now)
            return True
        return False

_token_bucket = TokenBucket(rate=30, burst=60)


# ====== 应用 ======

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 企业智能办公助手平台启动中...")
    logger.info(f"   环境: {settings.APP_ENV}  模型: {settings.LLM_MODEL}  限流: 30 req/s")
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
        "http://localhost:5173", "http://localhost:3000",
        "http://127.0.0.1:5173", "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 速率限制中间件
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    if path in ("/", "/api/health", "/docs", "/redoc", "/openapi.json"):
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
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({duration:.2f}s)")
    return response


# ====== 路由 ======
from app.api import chat, knowledge, tools, monitoring, auth, eval

app.include_router(chat.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api/knowledge")
app.include_router(tools.router, prefix="/api/tools")
app.include_router(monitoring.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(eval.router, prefix="/api")


@app.get("/", tags=["系统"])
async def root():
    return {
        "name": "企业智能办公助手平台 API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health", tags=["系统"])
async def health_check():
    return {"status": "ok", "version": "1.0.0", "llm_model": settings.LLM_MODEL}


@app.get("/api/info", tags=["系统"])
async def system_info():
    info = {"version": "1.0.0", "llm_model": settings.LLM_MODEL, "services": {}}
    for w in settings.validate():
        logger.warning(f"配置警告: {w}")
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        r.ping(); r.close()
        info["services"]["redis"] = "connected"
    except Exception as e:
        info["services"]["redis"] = f"unavailable ({e})"
    try:
        from app.rag.store import get_vector_store
        store = get_vector_store()
        info["services"]["chromadb"] = f"connected ({store._collection.count()} chunks)"
    except Exception as e:
        info["services"]["chromadb"] = f"unavailable ({e})"
    return info


# ====== 直接启动 ======
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
