-- LangSmith trace data storage and integration with Grafana

CREATE TABLE IF NOT EXISTS langsmith_traces (
    id                  BIGSERIAL PRIMARY KEY,
    ls_run_id           TEXT NOT NULL UNIQUE,
    request_id          UUID,
    created_at          TIMESTAMPTZ NOT NULL,
    started_at          TIMESTAMPTZ,
    ended_at            TIMESTAMPTZ,
    run_type            TEXT NOT NULL,
    run_name            TEXT NOT NULL,
    status              TEXT,
    input_data          JSONB,
    output_data         JSONB,
    error_message       TEXT,
    metadata            JSONB,
    latency_ms          INTEGER,
    cost_usd            FLOAT,
    ls_provider         TEXT,
    ls_model_name       TEXT,
    input_tokens        INTEGER,
    output_tokens       INTEGER,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    INDEX idx_langsmith_request_id (request_id),
    INDEX idx_langsmith_created (created_at),
    INDEX idx_langsmith_run_name (run_name)
);

-- Link LangSmith traces to gateway usage events
CREATE OR REPLACE VIEW dash_traces AS
SELECT
    t.request_id,
    t.run_name,
    t.status,
    t.created_at,
    t.latency_ms,
    t.cost_usd,
    t.ls_provider,
    t.ls_model_name,
    t.input_tokens,
    t.output_tokens,
    CASE
        WHEN t.input_data IS NOT NULL THEN json_extract_path_text(t.input_data::text, 'question')
        WHEN t.input_data IS NOT NULL THEN json_extract_path_text(t.input_data::text, 'text')
    END AS input_summary,
    CASE
        WHEN t.output_data IS NOT NULL THEN substring(json_extract_path_text(t.output_data::text, 'answer'), 1, 100)
        WHEN t.output_data IS NOT NULL THEN substring(json_extract_path_text(t.output_data::text, 'response'), 1, 100)
    END AS output_summary,
    u.tenant_id,
    u.tenant,
    u.status AS gateway_status,
    u.http_status,
    t.ls_run_id
FROM langsmith_traces t
LEFT JOIN dash_calls u ON u.request_id = t.request_id;

-- LangSmith cost aggregation by tenant
CREATE OR REPLACE VIEW dash_langsmith_costs AS
SELECT
    DATE_TRUNC('hour', t.created_at) AS hour,
    t.ls_provider,
    t.ls_model_name,
    COUNT(*) AS call_count,
    SUM(t.input_tokens) AS total_input_tokens,
    SUM(t.output_tokens) AS total_output_tokens,
    SUM(t.cost_usd) AS total_cost_usd,
    AVG(t.latency_ms) AS avg_latency_ms
FROM langsmith_traces t
WHERE t.created_at >= NOW() - INTERVAL '30 days'
GROUP BY DATE_TRUNC('hour', t.created_at), t.ls_provider, t.ls_model_name
ORDER BY hour DESC;

-- Grant permissions to Grafana read-only role
GRANT SELECT ON langsmith_traces, dash_traces, dash_langsmith_costs TO gate_readonly;
