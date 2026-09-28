CREATE TABLE IF NOT EXISTS model_prices (
    id               SERIAL PRIMARY KEY,
    provider         TEXT NOT NULL,
    model            TEXT NOT NULL,
    input_per_mtok   NUMERIC(10,4) NOT NULL,
    output_per_mtok  NUMERIC(10,4) NOT NULL,
    effective_from   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, model, effective_from)
);

ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS monthly_budget_usd NUMERIC(12,6) NOT NULL DEFAULT 5,
    ADD COLUMN IF NOT EXISTS soft_limit_pct INTEGER NOT NULL DEFAULT 80,
    ADD COLUMN IF NOT EXISTS downgrade_model TEXT;

ALTER TABLE usage_events
    ADD COLUMN IF NOT EXISTS routed_model TEXT,
    ADD COLUMN IF NOT EXISTS cost_usd NUMERIC(12,8);
