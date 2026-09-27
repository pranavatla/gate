CREATE TABLE IF NOT EXISTS usage_events (
    id               BIGSERIAL PRIMARY KEY,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    request_id       UUID NOT NULL UNIQUE,
    tenant_id        INTEGER NOT NULL REFERENCES tenants(id),
    key_prefix       TEXT NOT NULL,
    requested_model  TEXT NOT NULL,
    provider         TEXT NOT NULL,
    resolved_model   TEXT,
    status           TEXT NOT NULL,
    http_status      INTEGER NOT NULL,
    input_tokens     INTEGER NOT NULL DEFAULT 0,
    output_tokens    INTEGER NOT NULL DEFAULT 0,
    latency_ms       INTEGER NOT NULL,
    error            TEXT
);

CREATE INDEX IF NOT EXISTS usage_events_tenant_time
    ON usage_events (tenant_id, created_at);

CREATE OR REPLACE FUNCTION forbid_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'usage_events is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER usage_events_append_only
    BEFORE UPDATE OR DELETE ON usage_events
    FOR EACH ROW EXECUTE FUNCTION forbid_change();
