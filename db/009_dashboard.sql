ALTER TABLE usage_events
    ADD COLUMN IF NOT EXISTS provider_ms INTEGER;

CREATE OR REPLACE VIEW dash_calls AS
SELECT e.created_at,
       t.name AS tenant,
       a.name AS agent,
       e.run_id,
       e.status,
       e.http_status,
       e.requested_model,
       e.routed_model,
       e.cache_status,
       e.stop_reason,
       e.input_tokens,
       e.output_tokens,
       e.cost_usd,
       e.latency_ms,
       e.provider_ms,
       e.latency_ms - e.provider_ms AS gateway_ms,
       coalesce(cardinality(e.attempted_models), 0) AS attempts,
       e.policy_actions,
       e.tool_calls
FROM usage_events e
JOIN tenants t ON t.id = e.tenant_id
LEFT JOIN agents a ON a.id = e.agent_id;

CREATE OR REPLACE VIEW dash_budgets AS
SELECT t.name AS tenant,
       t.monthly_budget_usd AS budget_usd,
       coalesce(sum(e.cost_usd), 0) AS spent_usd,
       round(100 * coalesce(sum(e.cost_usd), 0) / NULLIF(t.monthly_budget_usd, 0), 1) AS used_pct
FROM tenants t
LEFT JOIN usage_events e
       ON e.tenant_id = t.id AND e.created_at >= date_trunc('month', now())
GROUP BY t.id;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gate_readonly') THEN
        CREATE ROLE gate_readonly LOGIN;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE gate TO gate_readonly;
GRANT USAGE ON SCHEMA public TO gate_readonly;
GRANT SELECT ON dash_calls, dash_budgets TO gate_readonly;
