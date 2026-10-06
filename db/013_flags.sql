CREATE TABLE IF NOT EXISTS feature_flags (
    id           SERIAL PRIMARY KEY,
    flag         TEXT NOT NULL,
    tenant_id    INTEGER REFERENCES tenants(id),
    enabled      BOOLEAN NOT NULL DEFAULT FALSE,
    rollout_pct  INTEGER NOT NULL DEFAULT 100 CHECK (rollout_pct BETWEEN 0 AND 100),
    note         TEXT,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS feature_flags_scope
    ON feature_flags (flag, COALESCE(tenant_id, 0));