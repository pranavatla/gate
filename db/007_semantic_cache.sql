CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS semantic_cache (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   INTEGER NOT NULL REFERENCES tenants(id),
    scope       TEXT NOT NULL,
    question    TEXT NOT NULL,
    embedding   vector(1536) NOT NULL,
    response    JSONB NOT NULL,
    hits        INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS semantic_cache_embedding
    ON semantic_cache USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS semantic_cache_scope
    ON semantic_cache (tenant_id, scope, expires_at);

ALTER TABLE usage_events
    ADD COLUMN IF NOT EXISTS cache_status TEXT;
