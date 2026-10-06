"""Public, aggregate-only usage statistics: GET /v1/stats.

Read by obs.atla.in's status collector every 15 minutes. Only totals over whole windows leave the
gateway: no tenant names, keys, request IDs, prompts or responses. The result is cached for a
minute, so however often the endpoint is called, the database sees at most one query a minute.
"""

import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import db
from app.config import GATE_CHATBOT_TENANT

router = APIRouter(tags=["Stats"])

CACHE_SECONDS = 60
_cached: tuple[float, dict] | None = None

TOTALS = """
SELECT
    count(*)                                                        AS calls,
    count(*) FILTER (WHERE created_at >= $2)                        AS calls_24h,
    count(*) FILTER (WHERE status = 'ok')                           AS ok,
    count(*) FILTER (WHERE http_status >= 500)                      AS errors_5xx,
    count(*) FILTER (WHERE status IN ('blocked', 'rejected'))       AS blocked,
    count(*) FILTER (WHERE status = 'rate_limited')                 AS rate_limited,
    count(*) FILTER (WHERE status = 'over_budget')                  AS over_budget,
    count(*) FILTER (WHERE cache_status = 'hit')                    AS cache_hits,
    count(*) FILTER (WHERE cache_status IN ('hit', 'miss'))         AS cache_lookups,
    count(*) FILTER (WHERE coalesce(cardinality(attempted_models), 0) > 1) AS failovers,
    coalesce(sum(input_tokens), 0)                                  AS input_tokens,
    coalesce(sum(output_tokens), 0)                                 AS output_tokens,
    coalesce(sum(cost_usd), 0)                                      AS cost_usd,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms - provider_ms)
        FILTER (WHERE provider_ms IS NOT NULL)                      AS gateway_ms_p50,
    percentile_cont(0.9) WITHIN GROUP (ORDER BY provider_ms)
        FILTER (WHERE provider_ms IS NOT NULL)                      AS provider_ms_p90,
    percentile_cont(0.9) WITHIN GROUP (ORDER BY latency_ms)
        FILTER (WHERE status = 'ok')                                AS latency_ms_p90
FROM usage_events
WHERE created_at >= $1
"""

MODELS = """
SELECT routed_model AS model, count(*) AS calls,
       coalesce(sum(input_tokens + output_tokens), 0) AS tokens,
       coalesce(sum(cost_usd), 0) AS cost_usd
FROM usage_events
WHERE created_at >= $1 AND status = 'ok' AND routed_model IS NOT NULL
GROUP BY routed_model
ORDER BY calls DESC
"""

HOURLY = """
SELECT h.hour, count(e.id) AS calls
FROM generate_series(date_trunc('hour', $1::timestamptz), date_trunc('hour', $2::timestamptz) - interval '1 hour',
                     interval '1 hour') AS h(hour)
LEFT JOIN usage_events e ON e.created_at >= h.hour AND e.created_at < h.hour + interval '1 hour'
GROUP BY h.hour
ORDER BY h.hour
"""


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _num(v):
    return None if v is None else float(v)


async def collect(now: datetime | None = None) -> dict:
    end = (now or datetime.now(timezone.utc)).replace(second=0, microsecond=0)
    week, day = end - timedelta(days=7), end - timedelta(days=1)
    async with db.pool.acquire() as conn:
        t = await conn.fetchrow(TOTALS, week, day)
        models = await conn.fetch(MODELS, week)
        # Whole hours only, so the last bucket is never a partial one.
        hour_end = end.replace(minute=0)
        hourly = await conn.fetch(HOURLY, hour_end - timedelta(hours=24), hour_end)
    return {
        "service": "gate.atla.in",
        "generated_at": iso(end),
        "windows": {"24h": {"start": iso(day), "end": iso(end)}, "7d": {"start": iso(week), "end": iso(end)}},
        "source": "usage_events audit log (append-only), aggregated; no tenant, key or content data",
        "totals_7d": {
            "calls": t["calls"], "calls_24h": t["calls_24h"], "ok": t["ok"],
            "errors_5xx": t["errors_5xx"], "blocked": t["blocked"],
            "rate_limited": t["rate_limited"], "over_budget": t["over_budget"],
            "cache_hits": t["cache_hits"], "cache_lookups": t["cache_lookups"],
            "failovers": t["failovers"],
            "input_tokens": t["input_tokens"], "output_tokens": t["output_tokens"],
            "cost_usd": round(float(t["cost_usd"]), 6),
            "gateway_ms_p50": _num(t["gateway_ms_p50"]),
            "provider_ms_p90": _num(t["provider_ms_p90"]),
            "latency_ms_p90": _num(t["latency_ms_p90"]),
        },
        "models_7d": [
            {"model": r["model"], "calls": r["calls"], "tokens": r["tokens"], "cost_usd": round(float(r["cost_usd"]), 6)}
            for r in models
        ],
        "calls_hourly_24h": [r["calls"] for r in hourly],
    }

_chatbot_cached: tuple[float, dict] | None = None
CHATBOT_CACHE_SECONDS = 10

CHATBOT_TOTALS = """
SELECT
    t.name AS tenant,
    t.monthly_budget_usd AS budget_usd,
    coalesce((
        SELECT sum(cost_usd) FROM usage_events me
        WHERE me.tenant_id = t.id AND me.created_at >= date_trunc('month', now())
    ), 0) AS spent_usd,
    count(e.id) AS calls_7d,
    count(e.id) FILTER (WHERE e.created_at >= $2) AS calls_24h,
    count(e.id) FILTER (WHERE e.status = 'ok') AS ok,
    count(e.id) FILTER (WHERE e.status IN ('blocked', 'rejected')) AS blocked,
    count(e.id) FILTER (WHERE e.status = 'rate_limited') AS rate_limited,
    count(e.id) FILTER (WHERE e.status = 'over_budget') AS over_budget,
    count(e.id) FILTER (WHERE e.cache_status = 'hit') AS cache_hits,
    count(e.id) FILTER (WHERE e.cache_status IN ('hit', 'miss')) AS cache_lookups,
    max(e.created_at) AS last_call_at,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY e.latency_ms) FILTER (WHERE e.status = 'ok') AS latency_ms_p50,
    coalesce(sum(e.cost_usd), 0) AS cost_7d
FROM tenants t
LEFT JOIN usage_events e ON e.tenant_id = t.id AND e.created_at >= $1
WHERE t.name = $3
GROUP BY t.id
"""

CHATBOT_RECENT = """
SELECT e.created_at, e.status, e.http_status, e.routed_model, e.cache_status,
       e.latency_ms, e.provider_ms, e.cost_usd, e.policy_actions, e.error
FROM usage_events e
JOIN tenants t ON t.id = e.tenant_id
WHERE t.name = $1
ORDER BY e.created_at DESC
LIMIT 8
"""


def _safe_event(r) -> dict:
    return {
        "at": iso(r["created_at"]),
        "status": r["status"],
        "http_status": r["http_status"],
        "model": r["routed_model"],
        "cache": r["cache_status"],
        "latency_ms": r["latency_ms"],
        "provider_ms": r["provider_ms"],
        "cost_usd": round(float(r["cost_usd"] or 0), 8),
        "policy_actions": r["policy_actions"] or [],
        "error": r["error"],
    }


async def collect_chatbot(now: datetime | None = None) -> dict:
    end = (now or datetime.now(timezone.utc)).replace(second=0, microsecond=0)
    week, day = end - timedelta(days=7), end - timedelta(days=1)
    async with db.pool.acquire() as conn:
        totals = await conn.fetchrow(CHATBOT_TOTALS, week, day, GATE_CHATBOT_TENANT)
        recent = await conn.fetch(CHATBOT_RECENT, GATE_CHATBOT_TENANT)
    if totals is None:
        return {"service": "gate.atla.in", "tenant": GATE_CHATBOT_TENANT, "configured": False}
    budget = float(totals["budget_usd"] or 0)
    spent = float(totals["spent_usd"] or 0)
    used_pct = None if budget <= 0 else round(100 * spent / budget, 1)
    return {
        "service": "gate.atla.in",
        "tenant": GATE_CHATBOT_TENANT,
        "configured": True,
        "generated_at": iso(end),
        "source": "usage_events audit log for the gate page chatbot tenant; no prompts, responses, keys or request bodies",
        "budget": {"monthly_usd": budget, "spent_usd": round(spent, 6), "used_pct": used_pct},
        "totals_7d": {
            "calls": totals["calls_7d"],
            "calls_24h": totals["calls_24h"],
            "ok": totals["ok"],
            "blocked": totals["blocked"],
            "rate_limited": totals["rate_limited"],
            "over_budget": totals["over_budget"],
            "cache_hits": totals["cache_hits"],
            "cache_lookups": totals["cache_lookups"],
            "cost_usd": round(float(totals["cost_7d"] or 0), 6),
            "last_call_at": iso(totals["last_call_at"]) if totals["last_call_at"] else None,
            "latency_ms_p50": _num(totals["latency_ms_p50"]),
        },
        "recent": [_safe_event(r) for r in recent],
    }



@router.get("/v1/stats")
async def stats():
    global _cached
    now = time.monotonic()
    if _cached is None or now - _cached[0] > CACHE_SECONDS:
        _cached = (now, await collect())
    return JSONResponse(_cached[1], headers={"Cache-Control": f"public, max-age={CACHE_SECONDS}",
                                             "Access-Control-Allow-Origin": "*"})


@router.get("/v1/stats/chatbot")
async def chatbot_stats():
    global _chatbot_cached
    now = time.monotonic()
    if _chatbot_cached is None or now - _chatbot_cached[0] > CHATBOT_CACHE_SECONDS:
        _chatbot_cached = (now, await collect_chatbot())
    return JSONResponse(_chatbot_cached[1], headers={"Cache-Control": f"public, max-age={CHATBOT_CACHE_SECONDS}",
                                                     "Access-Control-Allow-Origin": "*"})
