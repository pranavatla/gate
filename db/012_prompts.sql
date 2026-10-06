CREATE TABLE IF NOT EXISTS prompt_versions (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER NOT NULL REFERENCES tenants(id),
    name        TEXT NOT NULL,
    version     INTEGER NOT NULL,
    body        TEXT NOT NULL,
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, name, version)
);

CREATE OR REPLACE TRIGGER prompt_versions_immutable
    BEFORE UPDATE OR DELETE ON prompt_versions
    FOR EACH ROW EXECUTE FUNCTION forbid_change();

CREATE TABLE IF NOT EXISTS prompt_rollouts (
    tenant_id          INTEGER NOT NULL REFERENCES tenants(id),
    name               TEXT NOT NULL,
    stable_version     INTEGER NOT NULL,
    candidate_version  INTEGER,
    candidate_pct      INTEGER NOT NULL DEFAULT 0
                       CHECK (candidate_pct BETWEEN 0 AND 100),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, name)
);

ALTER TABLE usage_events
    ADD COLUMN IF NOT EXISTS prompt_name    TEXT,
    ADD COLUMN IF NOT EXISTS prompt_version INTEGER;