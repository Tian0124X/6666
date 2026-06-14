"""
语义查询缓存 — 2026 优化: 向量相似度匹配 + Redis 持久化

策略：
- 精确匹配 (MD5 hash) 命中 → 直接返回 (0ms)
- 精确未命中 → 向量相似度匹配 (top-100 热查询, ~10ms)
- 相似度 >0.92 → 返回缓存结果
- TTL: 热门查询 1h，普通 10min
- Redis 不可用时自动降级本地内存
"""

import json
import hashlib
import logging
import threading
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)

CACHE_TTL_HIGH = 3600    # 1 小时（热门查询）
CACHE_TTL_LOW = 600      # 10 分钟（普通查询）
HIT_THRESHOLD = 3        # 命中 3 次标记为热门
MAX_SIMILARITY_CACHE = 100  # 向量相似度缓存条数上限


class QueryCache:
    """语义查询缓存层 — 精确匹配 + 向量相似度"""

    def __init__(self):
        self._redis = None
        self._available = False
        self._hit_counter: dict[str, int] = {}       # key → 命中次数
        self._local_cache: dict[str, dict] = {}       # key → result
        self._embedder = None                         # 懒加载
        self._lock = threading.Lock()

        # 向量相似度缓存: 仅存热查询的 embedding (top 100)
        self._hot_embeddings: dict[str, list[float]] = {}  # key → embedding_vector
        self._hot_keys: list[str] = []  # LRU 顺序

        self._try_connect()

    def _try_connect(self):
        try:
            import redis
            self._redis = redis.from_url(
                settings.REDIS_URL,
                socket_connect_timeout=2,
            )
            self._redis.ping()
            self._available = True
            logger.info("Redis 缓存层就绪")
        except Exception as e:
            self._available = False
            logger.warning(f"Redis 不可用，降级本地: {e}")

    def _get_embedder(self):
        """懒加载向量化器"""
        if self._embedder is None:
            try:
                from app.rag.embedder import BGEEmbeddings
                self._embedder = BGEEmbeddings()
            except Exception:
                pass
        return self._embedder

    def _semantic_hash(self, query: str) -> str:
        """精确匹配哈希"""
        import re
        normalized = re.sub(r'[^\w一-鿿]', '', query.lower().strip())
        return f"rag_cache:{hashlib.md5(normalized.encode()).hexdigest()[:12]}"

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """余弦相似度"""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _similarity_search(self, query: str) -> Optional[str]:
        """
        向量相似度搜索 — 在热查询中找语义相似的问题。

        返回匹配的缓存 key 或 None。
        """
        embedder = self._get_embedder()
        if embedder is None or not self._hot_embeddings:
            return None

        try:
            query_vec = embedder.embed_query(query)
            best_key = None
            best_sim = 0.0

            for key, vec in self._hot_embeddings.items():
                sim = self._cosine_similarity(query_vec, vec)
                if sim > best_sim:
                    best_sim = sim
                    best_key = key

            if best_sim >= 0.92 and best_key:
                logger.debug(f"向量相似缓存命中 (sim={best_sim:.3f}): {query[:50]}...")
                return best_key
        except Exception as e:
            logger.debug(f"向量相似搜索失败: {e}")
        return None

    def get(self, query: str) -> Optional[dict]:
        """查询缓存 — 精确 → 向量相似 → 未命中"""
        key = self._semantic_hash(query)

        # 1. 精确匹配
        if self._available and self._redis:
            try:
                cached = self._redis.get(key)
                if cached:
                    data = json.loads(cached)
                    self._mark_hit(key)
                    return data
            except Exception:
                self._available = False

        if key in self._local_cache:
            self._mark_hit(key)
            return self._local_cache[key]

        # 2. 向量相似度匹配
        sim_key = self._similarity_search(query)
        if sim_key:
            if self._available and self._redis:
                try:
                    cached = self._redis.get(sim_key)
                    if cached:
                        data = json.loads(cached)
                        self._mark_hit(sim_key)
                        return data
                except Exception:
                    pass
            if sim_key in self._local_cache:
                self._mark_hit(sim_key)
                return self._local_cache[sim_key]

        return None

    def _mark_hit(self, key: str):
        """标记命中 + 增加计数"""
        self._hit_counter[key] = self._hit_counter.get(key, 0) + 1

    def set(self, query: str, result: dict):
        """写入缓存 + 更新热查询向量索引"""
        key = self._semantic_hash(query)
        hit_count = self._hit_counter.get(key, 0)
        ttl = CACHE_TTL_HIGH if hit_count >= HIT_THRESHOLD else CACHE_TTL_LOW

        # Redis
        if self._available and self._redis:
            try:
                self._redis.setex(key, ttl, json.dumps(result, ensure_ascii=False))
            except Exception:
                self._available = False

        # 本地
        with self._lock:
            self._local_cache[key] = result
            if len(self._local_cache) > 1000:
                keys = list(self._local_cache.keys())[:200]
                for k in keys:
                    del self._local_cache[k]

        # 热查询向量索引更新
        embedder = self._get_embedder()
        if embedder and hit_count >= HIT_THRESHOLD and key not in self._hot_embeddings:
            try:
                query_vec = embedder.embed_query(query)
                with self._lock:
                    self._hot_embeddings[key] = query_vec
                    if key in self._hot_keys:
                        self._hot_keys.remove(key)
                    self._hot_keys.append(key)
                    # LRU 淘汰
                    if len(self._hot_keys) > MAX_SIMILARITY_CACHE:
                        oldest = self._hot_keys.pop(0)
                        self._hot_embeddings.pop(oldest, None)
            except Exception:
                pass

    def clear(self):
        """清空所有缓存"""
        if self._available and self._redis:
            try:
                keys = self._redis.keys("rag_cache:*")
                if keys:
                    self._redis.delete(*keys)
            except Exception:
                pass
        with self._lock:
            self._local_cache.clear()
            self._hot_embeddings.clear()
            self._hot_keys.clear()
        self._hit_counter.clear()

    @property
    def stats(self) -> dict:
        return {
            "available": self._available,
            "hot_queries": len(
                {k: v for k, v in self._hit_counter.items() if v >= HIT_THRESHOLD}
            ),
            "similarity_indexed": len(self._hot_embeddings),
            "total_tracked": len(self._hit_counter),
        }


# 全局单例
query_cache = QueryCache()
