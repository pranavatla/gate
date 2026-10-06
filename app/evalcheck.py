"""Compare an eval run with its baseline and flag regressions.

Usage:
    python -m app.evalcheck <run-id|latest>
    python -m app.evalcheck accept <run-id>     (a deliberate change: make this run the new baseline)
    python -m app.evalcheck exclude <run-id>    (a known-bad run: keep it out of every baseline)

The baseline is the last few finished ('done') runs of the same set on the
same route. A run is a REGRESSION when its score is below the baseline average
by more than the tolerance: the larger of 0.10 (about one fully wrong case in
ten) and twice the baseline's own run-to-run spread. The verdict is stored on
the run. A run that was flagged REGRESSION never joins a baseline, so a bad night cannot
lower the bar. If the baseline itself is too noisy to judge against (usually because
it contains a bad run), the verdict is NOISY_BASELINE instead of a guess.
Exit code 3 means regression and 4 means noisy baseline, so a scheduler can alert on both.
"""
import asyncio
import json
import statistics
import sys
from decimal import Decimal

import asyncpg

from app.config import DATABASE_URL

BASELINE_RUNS = 5
MIN_BASELINE = 3
MIN_DROP = 0.10
MAX_TOLERANCE = 0.25
EPS = 1e-6

BASELINE_SQL = """
SELECT id, avg_score, avg_latency_ms, prompt_name, prompt_version
FROM eval_runs
WHERE set_id = $1 AND route = $2 AND status = 'done' AND id < $3
  AND COALESCE(verdict, '') NOT IN ('REGRESSION', 'EXCLUDED')
  AND id >= COALESCE((SELECT max(id) FROM eval_runs
                      WHERE set_id = $1 AND route = $2 AND verdict = 'ACCEPTED'), 0)
ORDER BY id DESC LIMIT $4
"""

FLIPPED_SQL = """
SELECT c.case_key, r.score, r.judge_reason, left(r.answer, 160) AS answer
FROM eval_results r JOIN eval_cases c ON c.id = r.case_id
WHERE r.run_id = $1 AND r.passed IS FALSE
  AND NOT EXISTS (
      SELECT 1 FROM eval_results b
      WHERE b.case_id = r.case_id AND b.run_id = ANY($2::int[]) AND b.passed IS NOT TRUE)
ORDER BY c.id
"""


def verdict_for(status: str, score: float | None, baseline: list[float]) -> tuple[str, dict]:
    """Pure decision logic, no database. Easy to unit test."""
    if status != "done" or score is None:
        return "UNRELIABLE", {"reason": f"run status is '{status}', so it is not compared"}
    if len(baseline) < MIN_BASELINE:
        return "BUILDING_BASELINE", {"baseline_runs": len(baseline), "needed": MIN_BASELINE}
    mean = statistics.fmean(baseline)
    spread = statistics.stdev(baseline)
    tolerance = max(MIN_DROP, 2 * spread)
    change = score - mean
    detail = {"baseline_runs": len(baseline), "baseline_mean": round(mean, 4),
              "baseline_spread": round(spread, 4), "tolerance": round(tolerance, 4),
              "change": round(change, 4)}
    if tolerance > MAX_TOLERANCE:
        detail["note"] = ("the baseline runs disagree too much to judge against; check baseline_scores "
                          "and exclude any bad run")
        return "NOISY_BASELINE", detail
    if -change + EPS >= tolerance:
        return "REGRESSION", detail
    if change + EPS >= tolerance:
        return "IMPROVED", detail
    return "OK", detail


async def accept(run_id: str):
    conn = await asyncpg.connect(DATABASE_URL)
    result = await conn.execute(
        "UPDATE eval_runs SET verdict = 'ACCEPTED', checked_at = now() WHERE id = $1 AND status = 'done'",
        int(run_id),
    )
    await conn.close()
    if result.endswith(" 0"):
        sys.exit("No finished run with that id")
    print(f"Run {run_id} is now the baseline start for its set and route")


async def exclude(run_id: str):
    conn = await asyncpg.connect(DATABASE_URL)
    result = await conn.execute(
        "UPDATE eval_runs SET verdict = 'EXCLUDED', checked_at = now() WHERE id = $1", int(run_id)
    )
    await conn.close()
    if result.endswith(" 0"):
        sys.exit("No such eval run")
    print(f"Run {run_id} will no longer be used in any baseline")


async def main(which: str = "latest"):
    conn = await asyncpg.connect(DATABASE_URL)
    run = (await conn.fetchrow("SELECT * FROM eval_runs ORDER BY id DESC LIMIT 1") if which == "latest"
           else await conn.fetchrow("SELECT * FROM eval_runs WHERE id = $1", int(which)))
    if run is None:
        sys.exit("No such eval run")

    base = await conn.fetch(BASELINE_SQL, run["set_id"], run["route"], run["id"], BASELINE_RUNS)
    score = float(run["avg_score"]) if run["avg_score"] is not None else None
    verdict, detail = verdict_for(run["status"], score, [float(b["avg_score"]) for b in base])

    if verdict in ("OK", "IMPROVED", "REGRESSION", "NOISY_BASELINE"):
        detail["baseline_scores"] = {str(b["id"]): float(b["avg_score"]) for b in base}
    if base and (run["prompt_name"], run["prompt_version"]) != (base[0]["prompt_name"], base[0]["prompt_version"]):
        detail["prompt_changed"] = (f"{base[0]['prompt_name']}@{base[0]['prompt_version']} -> "
                                    f"{run['prompt_name']}@{run['prompt_version']}")
    lat = [b["avg_latency_ms"] for b in base if b["avg_latency_ms"] is not None]
    if lat and run["avg_latency_ms"] and run["avg_latency_ms"] > 2 * statistics.fmean(lat) \
            and run["avg_latency_ms"] - statistics.fmean(lat) > 1000:
        detail["latency_warning"] = f"{run['avg_latency_ms']}ms vs baseline {int(statistics.fmean(lat))}ms"

    flipped = []
    if verdict == "REGRESSION":
        flipped = await conn.fetch(FLIPPED_SQL, run["id"], [b["id"] for b in base])
        detail["flipped_cases"] = [f["case_key"] for f in flipped]

    await conn.execute(
        "UPDATE eval_runs SET verdict = $2, verdict_detail = $3::jsonb, baseline_score = $4, checked_at = now() "
        "WHERE id = $1",
        run["id"], verdict, json.dumps(detail),
        Decimal(str(detail["baseline_mean"])) if "baseline_mean" in detail else None,
    )
    await conn.close()

    print(f"Run {run['id']} ({run['route']}, score {score}): {verdict}")
    for k, v in detail.items():
        if k != "flipped_cases":
            print(f"  {k}: {v}")
    for f in flipped:
        print(f"  FLIPPED {f['case_key']} score={f['score']}: {f['judge_reason']}")
        print(f"          answer: {f['answer']!r}")
    if verdict == "REGRESSION":
        sys.exit(3)
    if verdict == "NOISY_BASELINE":
        sys.exit(4)
    if verdict == "UNRELIABLE":
        sys.exit(5)


if __name__ == "__main__":
    if sys.argv[1:2] == ["accept"] and len(sys.argv) == 3:
        asyncio.run(accept(sys.argv[2]))
    elif sys.argv[1:2] == ["exclude"] and len(sys.argv) == 3:
        asyncio.run(exclude(sys.argv[2]))
    else:
        asyncio.run(main(*sys.argv[1:2]))