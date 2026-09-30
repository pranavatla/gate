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


@router.get("/v1/stats")
async def stats():
    global _cached
    now = time.monotonic()
    if _cached is None or now - _cached[0] > CACHE_SECONDS:
        _cached = (now, await collect())
    return JSONResponse(_cached[1], headers={"Cache-Control": f"public, max-age={CACHE_SECONDS}",
                                             "Access-Control-Allow-Origin": "*"})
