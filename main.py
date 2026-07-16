"""知识库 RAG 的 FastAPI 入口。"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger(__name__)
_model_status = {"embedding": False, "reranker": False}


class TokenBucket:
    """按客户端 IP 限制 RAG 请求速率。"""

    def __init__(self, rate: int = 20, burst: int = 40) -> None:
        self.rate = rate
        self.burst = burst
        self.buckets: dict[str, tuple[float, float]] = {}

    def consume(self, key: str) -> bool:
        now = time.time()
        tokens, previous = self.buckets.get(key, (self.burst, now))
        tokens = min(self.burst, tokens + (now - previous) * self.rate)
        self.buckets[key] = (tokens - 1, now) if tokens >= 1 else (tokens, now)
        return tokens >= 1


_bucket = TokenBucket()


def _warm_models() -> None:
    """进程启动时预热 embedding，避免首个用户请求承担下载与加载延迟。"""
    try:
        from app.rag.embedder import get_embedding_model

        model = get_embedding_model()
        _ = model.model
        _model_status["embedding"] = True
        logger.info("知识库 RAG embedding 预热完成")
    except Exception as exc:
        logger.warning("embedding 预热失败，首次请求将重试: %s", exc)

    if settings.RAG_ONLINE_RERANK:
        try:
            from app.rag.reranker import get_reranker

            get_reranker()
            _model_status["reranker"] = True
            logger.info("知识库 RAG reranker 预热完成")
        except Exception as exc:
            logger.warning("reranker 预热失败，线上请求将回退 RRF: %s", exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("知识库 RAG 启动中")
    asyncio.create_task(asyncio.to_thread(_warm_models))
    yield
    logger.info("知识库 RAG 已停止")


app = FastAPI(
    title="知识库 RAG API",
    description="基于 PostgreSQL + pgvector 的可追溯知识库问答服务",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def protect_and_log(request: Request, call_next):
    """对公开接口限流并输出易读的请求耗时。"""
    if request.url.path not in {"/", "/api/health", "/docs", "/openapi.json"}:
        client = request.client.host if request.client else "unknown"
        if not _bucket.consume(client):
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后重试")
    started = time.perf_counter()
    response = await call_next(request)
    logger.info("%s %s -> %s (%.0fms)", request.method, request.url.path, response.status_code,
                (time.perf_counter() - started) * 1000)
    return response


from app.api import auth, rag

app.include_router(auth.router, prefix="/api")
app.include_router(rag.router, prefix="/api/rag")


@app.get("/", tags=["系统"])
async def root():
    return {"name": "知识库 RAG", "version": "2.0.0", "docs": "/docs", "health": "/api/health"}


@app.get("/api/health", tags=["系统"])
async def health_check():
    return {
        "status": "ok",
        "version": "2.0.0",
        "embedding_ready": _model_status["embedding"],
        "reranker_ready": _model_status["reranker"],
    }
