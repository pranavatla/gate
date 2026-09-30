CREATE TABLE IF NOT EXISTS okf_bundles (
    tenant_id   INTEGER NOT NULL REFERENCES tenants(id),
    bundle_id   TEXT NOT NULL,
    documents   JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, bundle_id)
);
