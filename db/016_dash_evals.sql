CREATE OR REPLACE VIEW dash_evals AS
SELECT r.id AS run_id,
       r.started_at,
       r.finished_at,
       t.name AS tenant,
       s.name AS eval_set,
       r.route,
       r.prompt_name,
       r.prompt_version,
       r.triggered_by,
       r.status,
       r.n_cases,
       r.n_errors,
       r.avg_score,
       r.pass_rate,
       r.avg_latency_ms,
       r.cost_usd,
       r.verdict,
       r.baseline_score
FROM eval_runs r
JOIN eval_sets s ON s.id = r.set_id
JOIN tenants t ON t.id = s.tenant_id;

GRANT SELECT ON dash_evals TO gate_readonly;
