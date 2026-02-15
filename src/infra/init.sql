-- ============================================================
-- Internal Knowledge Assistant — PostgreSQL Schema
-- Uses pgvector extension for embedding storage
-- ============================================================

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- Tenants
-- ============================================================
CREATE TABLE tenants (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(255) NOT NULL,
    slug        VARCHAR(100) NOT NULL UNIQUE,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tenants_slug ON tenants(slug);

-- ============================================================
-- Documents — source material uploaded by tenants
-- ============================================================
CREATE TABLE documents (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title       VARCHAR(500) NOT NULL,
    content     TEXT NOT NULL,
    doc_type    VARCHAR(50) NOT NULL DEFAULT 'markdown',  -- markdown, text, pdf
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_documents_tenant ON documents(tenant_id);

-- ============================================================
-- Document Chunks — chunked pieces for RAG retrieval
-- ============================================================
CREATE TABLE document_chunks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    token_count     INTEGER NOT NULL DEFAULT 0,
    embedding       vector(384),  -- matches EMBEDDING_DIMENSION
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Critical: tenant_id index for scoped vector search
CREATE INDEX idx_chunks_tenant ON document_chunks(tenant_id);
CREATE INDEX idx_chunks_document ON document_chunks(document_id);

-- HNSW index for fast approximate nearest-neighbour search, scoped per tenant
-- Using cosine distance (<=>) which is standard for text embeddings
CREATE INDEX idx_chunks_embedding ON document_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ============================================================
-- AI Requests — audit log of every query
-- ============================================================
CREATE TABLE ai_requests (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    question        TEXT NOT NULL,
    answer          TEXT,
    sources         JSONB DEFAULT '[]',     -- array of {chunk_id, document_title, score}
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, completed, refused, error
    refused_reason  TEXT,
    prompt_tokens   INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens    INTEGER DEFAULT 0,
    model_used      VARCHAR(100),
    latency_ms      INTEGER,
    cached          BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_requests_tenant ON ai_requests(tenant_id);
CREATE INDEX idx_requests_status ON ai_requests(status);
CREATE INDEX idx_requests_created ON ai_requests(created_at DESC);

-- ============================================================
-- Feedback — human evaluation of AI outputs
-- ============================================================
CREATE TABLE feedback (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id      UUID NOT NULL REFERENCES ai_requests(id) ON DELETE CASCADE,
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    rating          SMALLINT CHECK (rating BETWEEN 1 AND 5),
    comment         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_feedback_request ON feedback(request_id);

-- ============================================================
-- Seed a default tenant for development
-- ============================================================
INSERT INTO tenants (id, name, slug) VALUES
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Aura Wellness', 'aura-wellness'),
    ('b1eebc99-9c0b-4ef8-bb6d-6bb9bd380b22', 'Demo Corp', 'demo-corp');
