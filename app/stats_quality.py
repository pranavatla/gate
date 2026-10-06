"""Public, aggregate-only quality statistics: GET /v1/stats/evals.

Feeds the live dashboard on the gateway's home page. Only counts, scores and verdicts of the nightly
evaluation runs leave the gateway: no questions, answers, judge text, prompt text, tenant names or
keys. Like /v1/stats, the result is cached for a minute, so the database sees at most one round of
queries a minute however often the endpoint is called.
"""

import time
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import db

router = APIRouter(tags=["Stats"])

CACHE_SECONDS = 60
RUN_LIMIT = 60
_cached: tuple[float, dict] | None = None

TOTALS = """
SELECT
    (SELECT count(*) FROM eval_runs)                          AS runs,
    (SELECT count(*) FROM eval_results)                       AS graded_answers,
    (SELECT count(*) FROM eval_cases)                         AS cases,
    (SELECT count(*) FROM eval_sets)                          AS sets,
    (SELECT count(*) FROM prompt_versions)                    AS prompt_versions,
    (SELECT coalesce(sum(cost_usd), 0) FROM eval_runs)        AS cost_usd,
    (SELECT max(coalesce(finished_at, started_at)) FROM eval_runs) AS last_run_at
"""

SETS = """
SELECT s.name AS name, count(c.id) AS cases
FROM eval_sets s
LEFT JOIN eval_cases c ON c.set_id = s.id
GROUP BY s.name
ORDER BY s.name
"""

VERDICTS = """
SELECT coalesce(verdict, 'UNCHECKED') AS verdict, count(*) AS runs
FROM eval_runs
GROUP BY 1
ORDER BY 2 DESC
"""

RUNS = """
SELECT run_id, started_at, finished_at, eval_set, prompt_name, prompt_version, status,
       n_cases, n_errors, avg_score, pass_rate, avg_latency_ms, cost_usd, verdict, baseline_score
FROM dash_evals
ORDER BY started_at DESC, run_id DESC
LIMIT $1
"""


def iso(t: datetime | None) -> str | None:
    if t is None:
        return None
    return t.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _num(v, digits: int | None = None):
    if v is None:
        return None
    v = float(v)
    return round(v, digits) if digits is not None else v


def _run(r) -> dict:
    prompt = f"{r['prompt_name']}@{r['prompt_version']}" if r["prompt_name"] else None
    return {
        "run_id": r["run_id"],
        "at": iso(r["finished_at"] or r["started_at"]),
        "set": r["eval_set"],
        "prompt": prompt,
        "status": r["status"],
        "cases": r["n_cases"],
        "errors": r["n_errors"],
        "score": _num(r["avg_score"], 3),
        "pass_rate": _num(r["pass_rate"], 3),
        "latency_ms": _num(r["avg_latency_ms"], 0),
        "cost_usd": _num(r["cost_usd"], 6),
        "verdict": r["verdict"],
        "baseline": _num(r["baseline_score"], 3),
    }


async def collect(now: datetime | None = None) -> dict:
    end = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    async with db.pool.acquire() as conn:
        t = await conn.fetchrow(TOTALS)
        sets = await conn.fetch(SETS)
        verdicts = await conn.fetch(VERDICTS)
        rows = await conn.fetch(RUNS, RUN_LIMIT)
    runs = [_run(r) for r in rows]
    summary = []
    for s in sets:
        mine = [r for r in runs if r["set"] == s["name"]]
        # "latest" skips runs a person threw out of the baseline, so a deliberate experiment is not the headline.
        latest = next((r for r in mine if r["verdict"] != "EXCLUDED"), None)
        summary.append({"name": s["name"], "cases": s["cases"], "runs": len(mine), "latest": latest})
    return {
        "service": "gate.atla.in",
        "generated_at": iso(end),
        "source": "eval_runs, eval_results, eval_cases and prompt_versions, aggregated; "
                  "no questions, answers, judge text, prompt text, tenant or key data",
        "totals": {
            "runs": t["runs"],
            "graded_answers": t["graded_answers"],
            "cases": t["cases"],
            "sets": t["sets"],
            "prompt_versions": t["prompt_versions"],
            "cost_usd": round(float(t["cost_usd"]), 6),
            "last_run_at": iso(t["last_run_at"]),
            "verdicts": {v["verdict"]: v["runs"] for v in verdicts},
        },
        "sets": summary,
        "runs": runs,
    }


@router.get("/v1/stats/evals")
async def eval_stats():
    global _cached
    now = time.monotonic()
    if _cached is None or now - _cached[0] > CACHE_SECONDS:
        _cached = (now, await collect())
    return JSONResponse(_cached[1], headers={"Cache-Control": f"public, max-age={CACHE_SECONDS}",
                                             "Access-Control-Allow-Origin": "*"})
