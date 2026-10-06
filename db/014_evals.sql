CREATE TABLE IF NOT EXISTS eval_sets (
    id           SERIAL PRIMARY KEY,
    tenant_id    INTEGER NOT NULL REFERENCES tenants(id),
    name         TEXT NOT NULL,
    description  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, name)
);

CREATE TABLE IF NOT EXISTS eval_cases (
    id          SERIAL PRIMARY KEY,
    set_id      INTEGER NOT NULL REFERENCES eval_sets(id),
    case_key    TEXT NOT NULL,
    question    TEXT NOT NULL,
    reference   TEXT,
    checks      JSONB NOT NULL DEFAULT '{}',
    source      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (set_id, case_key)
);

CREATE OR REPLACE TRIGGER eval_cases_immutable
    BEFORE UPDATE OR DELETE ON eval_cases
    FOR EACH ROW EXECUTE FUNCTION forbid_change();

CREATE TABLE IF NOT EXISTS eval_runs (
    id              SERIAL PRIMARY KEY,
    set_id          INTEGER NOT NULL REFERENCES eval_sets(id),
    triggered_by    TEXT NOT NULL DEFAULT 'manual',
    route           TEXT NOT NULL,
    prompt_name     TEXT,
    prompt_version  INTEGER,
    judge_model     TEXT,
    status          TEXT NOT NULL DEFAULT 'running',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    n_cases         INTEGER NOT NULL DEFAULT 0,
    n_errors        INTEGER NOT NULL DEFAULT 0,
    avg_score       NUMERIC(5,4),
    pass_rate       NUMERIC(5,4),
    avg_latency_ms  INTEGER,
    cost_usd        NUMERIC(12,6)
);

CREATE INDEX IF NOT EXISTS eval_runs_trend
    ON eval_runs (set_id, route, started_at DESC);

CREATE TABLE IF NOT EXISTS eval_results (
    id             BIGSERIAL PRIMARY KEY,
    run_id         INTEGER NOT NULL REFERENCES eval_runs(id),
    case_id        INTEGER NOT NULL REFERENCES eval_cases(id),
    request_id     UUID,
    answer         TEXT,
    score          NUMERIC(5,4) CHECK (score BETWEEN 0 AND 1),
    passed         BOOLEAN,
    check_results  JSONB,
    judge_reason   TEXT,
    latency_ms     INTEGER,
    cost_usd       NUMERIC(12,6),
    error          TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, case_id)
);

CREATE OR REPLACE TRIGGER eval_results_immutable
    BEFORE UPDATE OR DELETE ON eval_results
    FOR EACH ROW EXECUTE FUNCTION forbid_change();