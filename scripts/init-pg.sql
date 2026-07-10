-- 企业智能办公助手 — PostgreSQL + pgvector 初始化
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 向量文档表 (pgvector)
CREATE TABLE IF NOT EXISTS vector_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source TEXT NOT NULL,
    filename TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1024),  -- BGE-M3 维度 1024
    metadata JSONB DEFAULT '{}',
    chunk_index INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- HNSW 索引 (pgvector 0.7+ 支持，性能接近 ChromaDB)
CREATE INDEX IF NOT EXISTS idx_vector_embedding
    ON vector_documents
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 32, ef_construction = 200);

-- 全文检索索引
CREATE INDEX IF NOT EXISTS idx_vector_content
    ON vector_documents
    USING gin (to_tsvector('simple', content));

-- 源文件去重索引
CREATE INDEX IF NOT EXISTS idx_vector_source
    ON vector_documents (source);

-- 查询缓存表
CREATE TABLE IF NOT EXISTS query_cache (
    cache_key TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    sources JSONB,
    hit_count INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP DEFAULT (NOW() + INTERVAL '1 hour')
);

CREATE INDEX IF NOT EXISTS idx_cache_expires
    ON query_cache (expires_at);
