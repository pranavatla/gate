CREATE TABLE IF NOT EXISTS agents (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER NOT NULL REFERENCES tenants(id),
    name        TEXT NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    policy      JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, name)
);

ALTER TABLE api_keys
    ADD COLUMN IF NOT EXISTS agent_id INTEGER REFERENCES agents(id);

ALTER TABLE usage_events
    ADD COLUMN IF NOT EXISTS agent_id    INTEGER REFERENCES agents(id),
    ADD COLUMN IF NOT EXISTS run_id      TEXT,
    ADD COLUMN IF NOT EXISTS tool_calls  TEXT[],
    ADD COLUMN IF NOT EXISTS stop_reason TEXT;

CREATE INDEX IF NOT EXISTS usage_events_run
    ON usage_events (run_id) WHERE run_id IS NOT NULL;
