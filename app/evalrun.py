"""Run an eval set against a model route and store the scores.

Usage:
    python -m app.evalrun <tenant>/<set-name> <route> [prompt@version]

Example:
    python -m app.evalrun atla-chatbot/facts-v1 anthropic/claude-haiku-4-5-20251001 atla-chatbot@1

Every case's question is sent through the gateway as the `evals` tenant (cache
bypass on, own budget). If a prompt is given, its text is used as the system
prompt, so you can test a prompt version before it ever reaches a real tenant.
Each answer is scored by rule checks and the LLM judge. The run and every
result are written to eval_runs and eval_results.
"""
import asyncio
import json
import os
import re
import sys
import time
import uuid
from decimal import Decimal

import asyncpg
import httpx

from app import scorers
from app.config import DATABASE_URL

EVAL_TENANT = os.getenv("EVAL_TENANT", "evals")
ANSWER_MAX_TOKENS = 300
CONCURRENCY = 3
RETRY_STATUS = {429, 500, 502, 503, 504}
NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

COST_SQL = "SELECT COALESCE(sum(cost_usd), 0) FROM usage_events WHERE request_id = ANY($1::uuid[])"
INSERT_RESULT = """
INSERT INTO eval_results
    (run_id, case_id, request_id, answer, score, passed, check_results,
     judge_reason, latency_ms, cost_usd, error)
VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11)
"""


def describe(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        return f"{e.response.status_code}: {e.response.text[:200]}"
    return f"{type(e).__name__}: {e}"[:300]


async def ask(client: httpx.AsyncClient, route: str, system: str | None, question: str):
    """One answer through the gateway. Returns (answer, request_id, latency_ms)."""
    body = {"model": route, "max_tokens": ANSWER_MAX_TOKENS, "temperature": 0,
            "messages": [{"role": "user", "content": question}]}
    if system:
        body["system"] = system
    for attempt in range(3):
        t0 = time.perf_counter()
        resp = await client.post(
            f"{scorers.GATE_URL}/v1/chat",
            headers={"Authorization": f"Bearer {scorers.GATE_KEY}"},
            json=body, timeout=60,
        )
        ms = int((time.perf_counter() - t0) * 1000)
        if resp.status_code in RETRY_STATUS and attempt < 2:
            await asyncio.sleep(2 * (attempt + 1))
            continue
        resp.raise_for_status()
        return resp.json()["content"].strip(), resp.headers.get("x-request-id"), ms


async def run_case(pool, client, sem, run_id, case, route, system) -> dict:
    async with sem:
        answer = rid = latency = judge_reason = score = passed = error = None
        check_results: dict[str, bool] = {}
        ids: list[str] = []
        try:
            answer, rid, latency = await ask(client, route, system, case["question"])
            if rid:
                ids.append(rid)
            checks = case["checks"]
            checks = json.loads(checks) if isinstance(checks, str) else (checks or {})
            check_results = scorers.run_checks(answer, checks)
            judge_score = None
            if case["reference"]:
                j = await scorers.judge(client, case["question"], case["reference"], answer)
                judge_score, judge_reason = j.score, j.reason
                if j.request_id:
                    ids.append(j.request_id)
            score, passed = scorers.combine(check_results, judge_score)
        except (httpx.HTTPError, scorers.JudgeError, ValueError) as e:
            error = describe(e)
        cost = await pool.fetchval(COST_SQL, [uuid.UUID(i) for i in ids]) if ids else None
        await pool.execute(
            INSERT_RESULT, run_id, case["id"], uuid.UUID(rid) if rid else None, answer,
            Decimal(str(score)) if score is not None else None, passed,
            json.dumps(check_results), judge_reason, latency, cost, error,
        )
        return {"key": case["case_key"], "score": score, "passed": passed, "latency": latency,
                "cost": cost, "error": error, "reason": judge_reason, "checks": check_results}


async def main(spec: str, route: str, prompt: str | None = None):
    tenant_name, _, set_name = spec.partition("/")
    if not NAME_RE.match(set_name or ""):
        sys.exit("Use tenant/set-name (e.g. atla-chatbot/facts-v1)")
    if "/" not in route:
        sys.exit("The route must look like provider/model-id")
    if not scorers.GATE_KEY:
        sys.exit("Set EVAL_GATE_KEY to the evals tenant's key")
    if route == scorers.JUDGE_MODEL:
        print(f"WARNING: the judge ({scorers.JUDGE_MODEL}) is the same model as the route under test. "
              "A model grading its own answers tends to score itself high; "
              "set EVAL_JUDGE_MODEL to a different model.")

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=4)
    system = prompt_name = prompt_version = None
    if prompt:
        prompt_name, _, v = prompt.partition("@")
        if not NAME_RE.match(prompt_name) or not v.isdigit():
            sys.exit("Give the prompt as name@version (e.g. atla-chatbot@1)")
        prompt_version = int(v)
        system = await pool.fetchval(
            "SELECT p.body FROM prompt_versions p JOIN tenants t ON t.id = p.tenant_id "
            "WHERE t.name = $1 AND p.name = $2 AND p.version = $3",
            EVAL_TENANT, prompt_name, prompt_version,
        )
        if system is None:
            sys.exit(f"Tenant '{EVAL_TENANT}' has no prompt {prompt} (publish it there first)")

    row = await pool.fetchrow(
        "SELECT s.id FROM eval_sets s JOIN tenants t ON t.id = s.tenant_id WHERE t.name = $1 AND s.name = $2",
        tenant_name, set_name,
    )
    if row is None:
        sys.exit(f"No eval set '{spec}'")
    cases = await pool.fetch(
        "SELECT id, case_key, question, reference, checks FROM eval_cases WHERE set_id = $1 ORDER BY id", row["id"]
    )
    if not cases:
        sys.exit(f"Eval set '{spec}' has no cases")

    run_id = await pool.fetchval(
        "INSERT INTO eval_runs (set_id, triggered_by, route, prompt_name, prompt_version, judge_model, n_cases) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id",
        row["id"], os.getenv("EVAL_TRIGGER", "manual"), route, prompt_name, prompt_version,
        scorers.JUDGE_MODEL, len(cases),
    )
    print(f"Run {run_id}: {spec}  route={route}  prompt={prompt or '-'}  cases={len(cases)}")

    results: list[dict] = []
    status = "aborted"
    try:
        sem = asyncio.Semaphore(CONCURRENCY)
        async with httpx.AsyncClient() as client:
            results = await asyncio.gather(
                *(run_case(pool, client, sem, run_id, c, route, system) for c in cases)
            )
        scored = [r for r in results if r["error"] is None]
        n_err = len(results) - len(scored)
        status = "failed" if not scored else "partial" if n_err else "done"
    finally:
        scored = [r for r in results if r["error"] is None]
        lat = [r["latency"] for r in results if r["latency"] is not None]
        avg = lambda xs: sum(xs) / len(xs) if xs else None
        avg_score, pass_rate = avg([r["score"] for r in scored]), avg([1 if r["passed"] else 0 for r in scored])
        cost = sum((r["cost"] or 0 for r in results), Decimal(0))
        await pool.execute(
            "UPDATE eval_runs SET status=$2, finished_at=now(), n_errors=$3, avg_score=$4, pass_rate=$5, "
            "avg_latency_ms=$6, cost_usd=$7 WHERE id=$1",
            run_id, status, len(results) - len(scored),
            Decimal(str(round(avg_score, 4))) if avg_score is not None else None,
            Decimal(str(round(pass_rate, 4))) if pass_rate is not None else None,
            int(avg(lat)) if lat else None, cost,
        )
        await pool.close()

    for r in results:
        mark = "ERR " if r["error"] else "PASS" if r["passed"] else "FAIL"
        print(f"  {mark} {r['key']:<16} score={r['score']!s:<6} {r['latency'] or '-'}ms")
        if r["error"]:
            print(f"       error: {r['error']}")
        elif not r["passed"]:
            failed = [k for k, ok in r["checks"].items() if not ok]
            print(f"       judge: {r['reason']}" + (f"  failed checks: {failed}" if failed else ""))
    print(f"Run {run_id} {status}: avg_score={avg_score if avg_score is None else round(avg_score, 3)} "
          f"pass_rate={pass_rate if pass_rate is None else round(pass_rate, 3)} "
          f"errors={len(results) - len(scored)}/{len(results)} cost=${cost:.6f}")
    if status in ("failed", "aborted"):
        sys.exit(2)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python -m app.evalrun <tenant>/<set-name> <route> [prompt@version]")
    asyncio.run(main(*sys.argv[1:4]))