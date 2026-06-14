"""
PostgreSQL + pgvector 向量存储 — 2026 生产级替代 ChromaDB

借鉴: MaxKB (PostgreSQL+pgvector), Dify (统一数据库)
优势: 与 MySQL 合并运维 / 元数据过滤强 / HNSW 索引 / 全文检索
"""

import logging
import uuid
from typing import List, Optional
from datetime import datetime

from langchain_core.documents import Document
from app.config import settings
from app.rag.embedder import BGEEmbeddings

logger = logging.getLogger(__name__)

# 全局单例
_pg_store: Optional["PGVectorStore"] = None


class PGVectorStore:
    """PostgreSQL + pgvector 向量存储 (HNSW 索引, cosine 距离)"""

    COLLECTION_NAME = "enterprise_knowledge"
    DIMENSION = 512  # BGE-Small-ZH

    def __init__(self):
        self._conn = None
        self._cursor = None
        self._embedder: Optional[BGEEmbeddings] = None

    # ---- 连接管理 ----

    @property
    def conn(self):
        if self._conn is None or self._conn.closed:
            try:
                import psycopg2
                from pgvector.psycopg2 import register_vector
            except ImportError as e:
                raise RuntimeError(f"pgvector 依赖未安装: {e}") from e

            if not settings.PG_PASSWORD:
                raise RuntimeError("PG_PASSWORD 未配置，pgvector 不可用")

            self._conn = psycopg2.connect(
                host=settings.PG_HOST,
                port=settings.PG_PORT,
                dbname=settings.PG_DATABASE,
                user=settings.PG_USER,
                password=settings.PG_PASSWORD,
            )
            self._conn.autocommit = True
            register_vector(self._conn)
            logger.info("pgvector 连接就绪")
        return self._conn

    @property
    def embedder(self) -> BGEEmbeddings:
        if self._embedder is None:
            self._embedder = BGEEmbeddings()
        return self._embedder

    def is_available(self) -> bool:
        """检查 pgvector 是否可用"""
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT 1 FROM vector_documents LIMIT 0")
            cur.close()
            return True
        except Exception as e:
            logger.warning(f"pgvector 不可用: {e}")
            return False

    # ---- 向量操作 ----

    def add_documents(self, documents: List[Document], batch_size: int = 50) -> int:
        """批量添加文档向量"""
        texts = [doc.page_content for doc in documents]
        embeddings = self.embedder.embed_documents(texts)

        cur = self.conn.cursor()
        total = 0
        for i in range(0, len(documents), batch_size):
            batch_docs = documents[i:i + batch_size]
            batch_embs = embeddings[i:i + batch_size]
            rows = []
            for doc, emb in zip(batch_docs, batch_embs):
                rows.append((
                    str(uuid.uuid4()),
                    doc.metadata.get("source", ""),
                    doc.metadata.get("filename", "unknown"),
                    doc.page_content,
                    emb,
                    self._serialize_meta(doc.metadata),
                    doc.metadata.get("chunk_index", 0),
                ))
            cur.executemany(
                """INSERT INTO vector_documents (id, source, filename, content, embedding, metadata, chunk_index)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO NOTHING""",
                rows,
            )
            total += len(rows)
        cur.close()
        logger.info(f"pgvector: 已添加 {total} 个 chunks")
        return total

    def search(
        self, query: str, k: int = 5,
        where: Optional[dict] = None,
        fetch_k: int = 20,
    ) -> List[Document]:
        """混合检索: 向量相似度 (cosine) + 全文关键词"""
        query_embedding = self.embedder.embed_query(query)
        cur = self.conn.cursor()

        # 向量检索 (cosine 相似度)
        cur.execute(
            """SELECT content, metadata, source, filename,
                      1 - (embedding <=> %s::vector) AS similarity
               FROM vector_documents
               ORDER BY embedding <=> %s::vector
               LIMIT %s""",
            (query_embedding, query_embedding, fetch_k),
        )
        vector_results = cur.fetchall()

        # 关键词全文检索 (PostgreSQL tsvector)
        keywords = " | ".join(query.split())
        cur.execute(
            """SELECT content, metadata, source, filename,
                      ts_rank(to_tsvector('simple', content), to_tsquery('simple', %s)) AS rank
               FROM vector_documents
               WHERE to_tsvector('simple', content) @@ to_tsquery('simple', %s)
               ORDER BY rank DESC
               LIMIT %s""",
            (keywords, keywords, fetch_k),
        )
        text_results = cur.fetchall()
        cur.close()

        # RRF 融合 (简版: 按位置加权)
        docs = self._fuse_results(vector_results, text_results, k)
        return docs

    def _fuse_results(self, vector_rows, text_rows, k: int) -> List[Document]:
        """简化 RRF 融合: 向量结果 + 全文结果 → 去重取 top-k"""
        seen = set()
        docs = []
        # 向量结果优先
        for row in vector_rows:
            content, meta_json, source, filename, _ = row
            key = content[:200]
            if key not in seen:
                seen.add(key)
                docs.append(Document(
                    page_content=content,
                    metadata=self._deserialize_meta(meta_json, source, filename),
                ))
        # 全文结果补充
        for row in text_rows:
            content, meta_json, source, filename, _ = row
            key = content[:200]
            if key not in seen:
                seen.add(key)
                docs.append(Document(
                    page_content=content,
                    metadata=self._deserialize_meta(meta_json, source, filename),
                ))
        return docs[:k]

    def delete_by_source(self, source: str) -> int:
        """按源文件路径删除"""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM vector_documents WHERE source = %s", (source,))
        count = cur.rowcount
        cur.close()
        logger.info(f"pgvector: 已删除 {count} 条 (source={source})")
        return count

    def get_document_count(self) -> int:
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT COUNT(*) FROM vector_documents")
            return cur.fetchone()[0]
        except Exception:
            return 0

    def get_unique_sources(self) -> List[str]:
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT DISTINCT filename FROM vector_documents ORDER BY filename")
            return [r[0] for r in cur.fetchall()]
        except Exception:
            return []

    def clear_collection(self):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM vector_documents")
        count = cur.rowcount
        cur.close()
        logger.warning(f"pgvector: 已清空 ({count} 条)")

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()

    # ---- helpers ----

    def _serialize_meta(self, meta: dict) -> str:
        import json
        return json.dumps(meta, ensure_ascii=False, default=str)

    def _deserialize_meta(self, meta_json, source: str, filename: str) -> dict:
        import json
        try:
            meta = json.loads(meta_json) if isinstance(meta_json, str) else (meta_json or {})
        except (json.JSONDecodeError, TypeError):
            meta = {}
        meta["source"] = source
        meta["filename"] = filename
        return meta


def get_pgvector_store() -> Optional[PGVectorStore]:
    """获取 pgvector 存储实例 (懒加载)"""
    global _pg_store
    if _pg_store is None:
        store = PGVectorStore()
        if store.is_available():
            _pg_store = store
        else:
            _pg_store = False  # type: ignore
            return None
    return _pg_store if _pg_store is not False else None
