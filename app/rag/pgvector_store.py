"""纯 RAG 的 PostgreSQL + pgvector 存储层。"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from langchain_core.documents import Document

from app.config import settings
from app.rag.embedder import BGEEmbeddings, get_embedding_model
from app.rag.errors import EmbeddingDimensionMismatch

logger = logging.getLogger(__name__)
_pg_store: "PGVectorStore | None | bool" = None


def reciprocal_rank_fusion(
    vector_candidates: Iterable[dict[str, Any]],
    keyword_candidates: Iterable[dict[str, Any]],
    k: int = 60,
) -> list[dict[str, Any]]:
    """将向量与关键词候选做一次稳定的 RRF 融合。"""
    by_id: dict[str, dict[str, Any]] = {}
    scores: defaultdict[str, float] = defaultdict(float)
    for candidates in (vector_candidates, keyword_candidates):
        for position, candidate in enumerate(candidates, start=1):
            chunk_id = str(candidate["chunk_id"])
            by_id.setdefault(chunk_id, dict(candidate))
            scores[chunk_id] += 1 / (k + position)
    return [
        {**candidate, "score": round(scores[chunk_id], 8)}
        for chunk_id, candidate in sorted(
            by_id.items(), key=lambda item: (-scores[item[0]], item[0])
        )
    ]


class PGVectorStore:
    """唯一知识库后端：文档切片、向量检索、全文检索与证据读取。"""

    DIMENSION = settings.RAG_EMBEDDING_DIMENSION

    def __init__(self) -> None:
        self._conn = None
        self._embedder: BGEEmbeddings | None = None
        self._schema_ready = False

    @property
    def conn(self):
        if self._conn is None or self._conn.closed:
            try:
                import psycopg2
                from pgvector.psycopg2 import register_vector
            except ImportError as exc:
                raise RuntimeError(f"缺少 pgvector 依赖: {exc}") from exc
            if not settings.PG_PASSWORD:
                raise RuntimeError("未配置 PG_PASSWORD，无法使用知识库")
            self._conn = psycopg2.connect(
                host=settings.PG_HOST,
                port=settings.PG_PORT,
                dbname=settings.PG_DATABASE,
                user=settings.PG_USER,
                password=settings.PG_PASSWORD,
                connect_timeout=2,
            )
            self._conn.autocommit = True
            register_vector(self._conn)
        return self._conn

    @property
    def embedder(self) -> BGEEmbeddings:
        if self._embedder is None:
            self._embedder = get_embedding_model()
        return self._embedder

    def is_available(self) -> bool:
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT 1 FROM vector_documents LIMIT 0")
            cur.close()
            return True
        except Exception as exc:
            logger.warning("pgvector 不可用: %s", exc)
            return False

    def ensure_schema(self) -> None:
        """创建全文索引；旧表无需停机迁移即可继续读取。"""
        if self._schema_ready:
            return
        cur = self.conn.cursor()
        try:
            cur.execute(
                """ALTER TABLE vector_documents
                   ADD COLUMN IF NOT EXISTS search_vector tsvector
                   GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content, ''))) STORED"""
            )
            cur.execute(
                """CREATE INDEX IF NOT EXISTS idx_vector_documents_fts
                   ON vector_documents USING GIN (search_vector)"""
            )
            # QueryPlan 的显式过滤条件需要独立索引，避免退化为全表扫描。
            cur.execute(
                """CREATE INDEX IF NOT EXISTS idx_vector_documents_filename
                   ON vector_documents (filename)"""
            )
            cur.execute(
                """CREATE INDEX IF NOT EXISTS idx_vector_documents_file_type
                   ON vector_documents ((metadata ->> 'file_type'))"""
            )
            cur.execute(
                """CREATE INDEX IF NOT EXISTS idx_vector_documents_sheet
                   ON vector_documents ((metadata ->> 'sheet'))"""
            )
            cur.execute(
                """CREATE INDEX IF NOT EXISTS idx_vector_documents_page
                   ON vector_documents (((metadata ->> 'page')::integer))
                   WHERE (metadata ->> 'page') ~ '^[0-9]+$'"""
            )
            cur.execute(
                """CREATE INDEX IF NOT EXISTS idx_vector_documents_document_date
                   ON vector_documents ((metadata ->> 'document_date'))
                   WHERE (metadata ->> 'document_date') ~ '^\\d{4}-\\d{2}-\\d{2}$'"""
            )
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
                cur.execute(
                    """CREATE INDEX IF NOT EXISTS idx_vector_documents_content_trgm
                       ON vector_documents USING GIN (content gin_trgm_ops)"""
                )
                cur.execute(
                    """CREATE INDEX IF NOT EXISTS idx_vector_documents_filename_trgm
                       ON vector_documents USING GIN (filename gin_trgm_ops)"""
                )
            except Exception as exc:
                logger.info("未创建 trigram 索引，继续使用全文索引: %s", exc)
            self._schema_ready = True
        finally:
            cur.close()

    def embedding_dimension(self) -> int | None:
        cur = self.conn.cursor()
        try:
            cur.execute(
                """SELECT format_type(a.atttypid, a.atttypmod)
                   FROM pg_attribute a
                   WHERE a.attrelid = 'vector_documents'::regclass
                     AND a.attname = 'embedding' AND NOT a.attisdropped"""
            )
            row = cur.fetchone()
            match = re.fullmatch(r"vector\((\d+)\)", row[0]) if row else None
            return int(match.group(1)) if match else None
        finally:
            cur.close()

    def ensure_embedding_dimension(self) -> None:
        actual = self.embedding_dimension()
        if actual != self.DIMENSION:
            raise EmbeddingDimensionMismatch(
                f"知识库维度为 {actual or '未知'}，当前模型需要 {self.DIMENSION}；请重新索引。"
            )

    @staticmethod
    def _document_id(source: str, filename: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, source or filename))

    @staticmethod
    def _decode_meta(meta_json: Any, source: str, filename: str) -> dict[str, Any]:
        try:
            metadata = json.loads(meta_json) if isinstance(meta_json, str) else dict(meta_json or {})
        except (TypeError, ValueError):
            metadata = {}
        metadata["source"] = source
        metadata["filename"] = filename
        metadata.setdefault("document_id", PGVectorStore._document_id(source, filename))
        return metadata

    @staticmethod
    def _serialize_meta(metadata: dict[str, Any]) -> str:
        return json.dumps(metadata, ensure_ascii=False, default=str)

    def add_documents(self, documents: list[Document], batch_size: int = 50) -> int:
        """批量写入并补齐文档、切片和追溯身份。"""
        self.ensure_embedding_dimension()
        self.ensure_schema()
        cur = self.conn.cursor()
        total = 0
        try:
            for offset in range(0, len(documents), batch_size):
                batch = documents[offset: offset + batch_size]
                vectors = self.embedder.embed_documents([doc.page_content for doc in batch])
                rows = []
                for doc, embedding in zip(batch, vectors):
                    metadata = dict(doc.metadata)
                    source = str(metadata.get("source", ""))
                    filename = str(metadata.get("filename", "未命名文档"))
                    # splitter 的 chunk_id 仅是页内序号，不能作为数据库全局主键。
                    chunk_index = int(metadata.get("chunk_index", metadata.get("chunk_id", 0)))
                    chunk_id = str(uuid.uuid4())
                    document_id = str(metadata.get("document_id") or self._document_id(source, filename))
                    metadata.update({
                        "chunk_id": chunk_id,
                        "chunk_index": chunk_index,
                        "document_id": document_id,
                    })
                    rows.append((
                        chunk_id, source, filename, doc.page_content, embedding,
                        self._serialize_meta(metadata), chunk_index,
                    ))
                cur.executemany(
                    """INSERT INTO vector_documents
                       (id, source, filename, content, embedding, metadata, chunk_index)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    rows,
                )
                total += len(rows)
        finally:
            cur.close()
        return total

    def _keyword_terms(self, query: str) -> list[str]:
        try:
            import jieba
            terms = [term.strip() for term in jieba.cut(query) if len(term.strip()) >= 2]
        except ImportError:
            terms = [query.strip()] if query.strip() else []
        return list(dict.fromkeys(terms))[:6]

    @staticmethod
    def _identifier_terms(query: str) -> list[str]:
        """提取 SP0001 一类精确业务标识符，用于优先定位结构化行。"""
        terms = re.findall(r"\b[A-Za-z]{1,12}[-_]?\d{2,}\b", query.upper())
        return list(dict.fromkeys(terms))[:3]

    @staticmethod
    def _build_filter_clause(filters: dict[str, Any] | None) -> tuple[str, list[Any]]:
        """构建固定字段的参数化过滤 SQL，禁止将用户输入拼入语句。"""
        filters = filters or {}
        clauses: list[str] = []
        params: list[Any] = []
        filenames = [str(name) for name in filters.get("filenames", []) if str(name).strip()][:3]
        if filenames:
            filename_conditions: list[str] = []
            for filename in filenames:
                # 保留用户输入中的普通字符，转义 LIKE 通配符后才允许包含匹配。
                terms = [filename]
                stem = Path(filename).stem.strip()
                if len(stem) >= 2 and stem != filename:
                    terms.append(stem)
                like_conditions: list[str] = []
                for term in terms:
                    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                    like_conditions.append("filename ILIKE %s ESCAPE '\\'")
                    params.append(f"%{escaped}%")
                filename_conditions.append("(filename = %s OR " + " OR ".join(like_conditions) + ")")
                exact_index = len(params) - len(like_conditions)
                params.insert(exact_index, filename)
            clauses.append("(" + " OR ".join(filename_conditions) + ")")
        page_start = filters.get("page_start")
        page_end = filters.get("page_end")
        if isinstance(page_start, int) and isinstance(page_end, int):
            page_expression = "(metadata ->> 'page')"
            clauses.append(f"({page_expression} ~ '^[0-9]+$' AND {page_expression}::integer BETWEEN %s AND %s)")
            params.extend([min(page_start, page_end), max(page_start, page_end)])
        sheet = filters.get("sheet")
        if isinstance(sheet, str) and sheet.strip():
            clauses.append("metadata ->> 'sheet' = %s")
            params.append(sheet.strip())
        file_types = [str(file_type).lower() for file_type in filters.get("file_types", []) if str(file_type).strip()]
        if file_types:
            clauses.append("metadata ->> 'file_type' = ANY(%s)")
            params.append(file_types)
        document_date_start = filters.get("document_date_start")
        if isinstance(document_date_start, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", document_date_start):
            clauses.append("metadata ->> 'document_date' >= %s")
            params.append(document_date_start)
        document_date_end = filters.get("document_date_end")
        if isinstance(document_date_end, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", document_date_end):
            clauses.append("metadata ->> 'document_date' <= %s")
            params.append(document_date_end)
        return (" AND ".join(clauses) if clauses else "TRUE"), params

    def search(
        self, query: str, k: int = 5, fetch_k: int = 30, filters: dict[str, Any] | None = None,
    ) -> list[Document]:
        """执行一次向量与关键词召回，再以 RRF 融合。"""
        self.ensure_embedding_dimension()
        self.ensure_schema()
        embedding = self.embedder.embed_query(query)
        filter_clause, filter_params = self._build_filter_clause(filters)
        cur = self.conn.cursor()
        try:
            cur.execute(
                """SELECT id::text, content, metadata, source, filename,
                          1 - (embedding <=> %s::vector) AS raw_score
                   FROM vector_documents WHERE """ + filter_clause + """
                   ORDER BY embedding <=> %s::vector
                   LIMIT %s""",
                [embedding, *filter_params, embedding, fetch_k],
            )
            vector_rows = cur.fetchall()
            terms = self._keyword_terms(query)
            patterns = [f"%{term}%" for term in terms]
            if patterns:
                cur.execute(
                    """SELECT id::text, content, metadata, source, filename,
                              ts_rank(search_vector, websearch_to_tsquery('simple', %s)) AS raw_score
                       FROM vector_documents
                       WHERE (search_vector @@ websearch_to_tsquery('simple', %s)
                          OR content ILIKE ANY(%s)) AND """ + filter_clause + """
                       ORDER BY raw_score DESC, chunk_index ASC
                       LIMIT %s""",
                    [query, query, patterns, *filter_params, fetch_k],
                )
                keyword_rows = cur.fetchall()
            else:
                keyword_rows = []
            identifier_terms = self._identifier_terms(query)
            if identifier_terms:
                identifier_patterns = [f"%{term}%" for term in identifier_terms]
                cur.execute(
                    """SELECT id::text, content, metadata, source, filename, 1.0 AS raw_score
                       FROM vector_documents WHERE content ILIKE ANY(%s) AND """ + filter_clause + """
                       ORDER BY chunk_index ASC
                       LIMIT %s""",
                    [identifier_patterns, *filter_params, fetch_k],
                )
                identifier_rows = cur.fetchall()
            else:
                identifier_rows = []
        finally:
            cur.close()

        def to_candidate(row: tuple[Any, ...]) -> dict[str, Any]:
            chunk_id, content, meta_json, source, filename, raw_score = row
            return {
                "chunk_id": str(chunk_id),
                "content": content,
                "metadata": self._decode_meta(meta_json, source, filename),
                "raw_score": float(raw_score or 0),
            }

        fused = reciprocal_rank_fusion(
            [to_candidate(row) for row in vector_rows],
            [to_candidate(row) for row in keyword_rows],
        )
        # 精确标识符的命中行优先于语义近似块，防止表格中相邻商品抢占答案上下文。
        exact_candidates = [to_candidate(row) for row in identifier_rows]
        exact_ids = {candidate["chunk_id"] for candidate in exact_candidates}
        fused = [
            {**candidate, "score": 1.0 - position * 0.0001}
            for position, candidate in enumerate(exact_candidates)
        ] + [candidate for candidate in fused if candidate["chunk_id"] not in exact_ids]
        fused = fused[:k]
        docs = []
        for candidate in fused:
            metadata = dict(candidate["metadata"])
            metadata.update({"chunk_id": candidate["chunk_id"], "score": candidate["score"]})
            docs.append(Document(page_content=candidate["content"], metadata=metadata))
        return docs

    def get_evidence(self, document_id: str, chunk_id: str) -> dict[str, Any] | None:
        """返回命中切片及其相邻切片，供证据抽屉使用。"""
        cur = self.conn.cursor()
        try:
            cur.execute(
                """SELECT id::text, content, metadata, source, filename, chunk_index
                   FROM vector_documents WHERE id::text = %s""",
                (chunk_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            found_id, content, meta_json, source, filename, chunk_index = row
            metadata = self._decode_meta(meta_json, source, filename)
            if metadata["document_id"] != document_id:
                return None
            cur.execute(
                """SELECT id::text, content, metadata, chunk_index
                   FROM vector_documents
                   WHERE source = %s AND chunk_index BETWEEN %s AND %s
                   ORDER BY chunk_index""",
                (source, max(0, chunk_index - 1), chunk_index + 1),
            )
            nearby = []
            for near_id, near_content, near_meta, near_index in cur.fetchall():
                near_metadata = self._decode_meta(near_meta, source, filename)
                nearby.append({
                    "chunk_id": str(near_id), "content": near_content,
                    "page": near_metadata.get("page"), "chunk_index": near_index,
                })
            return {
                "document_id": document_id, "chunk_id": str(found_id), "filename": filename,
                "page": metadata.get("page"), "content": content, "nearby": nearby,
            }
        finally:
            cur.close()

    def resolve_document_path(self, document_id: str) -> tuple[str, str] | None:
        """按稳定文档身份解析受控的原文件路径。"""
        cur = self.conn.cursor()
        try:
            cur.execute("SELECT DISTINCT source, filename FROM vector_documents")
            for source, filename in cur.fetchall():
                if self._document_id(source, filename) == document_id:
                    return source, filename
            return None
        finally:
            cur.close()

    def delete_by_source(self, source: str) -> int:
        cur = self.conn.cursor()
        try:
            cur.execute("DELETE FROM vector_documents WHERE source = %s", (source,))
            return cur.rowcount
        finally:
            cur.close()

    def get_document_count(self) -> int:
        cur = self.conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM vector_documents")
            return int(cur.fetchone()[0])
        finally:
            cur.close()

    def get_unique_sources(self) -> list[str]:
        cur = self.conn.cursor()
        try:
            cur.execute("SELECT DISTINCT filename FROM vector_documents ORDER BY filename")
            return [row[0] for row in cur.fetchall()]
        finally:
            cur.close()

    def get_document_summaries(self) -> list[dict[str, Any]]:
        """按原文件汇总切片数，供知识库管理界面展示任务结果。"""
        cur = self.conn.cursor()
        try:
            cur.execute(
                """SELECT source, filename, COUNT(*),
                          MIN(metadata ->> 'file_sha256') AS file_sha256,
                          MAX(metadata ->> 'indexed_at') AS indexed_at,
                          MIN(metadata ->> 'document_date') AS document_date
                   FROM vector_documents
                   GROUP BY source, filename
                   ORDER BY filename"""
            )
            return [
                {
                    "source": source,
                    "filename": filename,
                    "chunks": int(chunks),
                    "document_id": self._document_id(source, filename),
                    "file_sha256": file_sha256,
                    "indexed_at": indexed_at,
                    "document_date": document_date,
                }
                for source, filename, chunks, file_sha256, indexed_at, document_date in cur.fetchall()
            ]
        finally:
            cur.close()

    def clear_collection(self) -> None:
        cur = self.conn.cursor()
        try:
            cur.execute("DELETE FROM vector_documents")
        finally:
            cur.close()


def get_pgvector_store() -> PGVectorStore | None:
    """获取进程级 pgvector 实例，不再回退到第二套知识库。"""
    global _pg_store
    if _pg_store is None or _pg_store is False:
        candidate = PGVectorStore()
        _pg_store = candidate if candidate.is_available() else False
    return _pg_store if isinstance(_pg_store, PGVectorStore) else None
