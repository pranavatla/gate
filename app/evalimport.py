"""Import hand-written eval cases from a JSONL file.

Usage:
    python -m app.evalimport <tenant>/<set-name> <file.jsonl>

Each line is one JSON object: case_key, question, optional reference, and optional
checks (contains, contains_any, not_contains, max_words). Re-running is safe:
a case that already exists is never changed, because cases are immutable.
"""
import asyncio
import json
import sys
from pathlib import Path

import asyncpg

from app.config import DATABASE_URL

ALLOWED_CHECKS = {"contains", "contains_any", "not_contains", "max_words"}


def parse_cases(text: str) -> list[dict]:
    cases: list[dict] = []
    seen: set[str] = set()
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            sys.exit(f"Line {n}: invalid JSON ({exc})")
        if not isinstance(row, dict):
            sys.exit(f"Line {n}: each line must be a JSON object")
        for field in ("case_key", "question"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                sys.exit(f"Line {n}: '{field}' is required")
        if row["case_key"] in seen:
            sys.exit(f"Line {n}: duplicate case_key '{row['case_key']}'")
        seen.add(row["case_key"])
        checks = row.get("checks", {})
        if not isinstance(checks, dict):
            sys.exit(f"Line {n}: 'checks' must be an object")
        unknown = set(checks) - ALLOWED_CHECKS
        if unknown:
            sys.exit(f"Line {n}: unknown check(s) {sorted(unknown)}; allowed: {sorted(ALLOWED_CHECKS)}")
        cases.append({
            "case_key": row["case_key"].strip(),
            "question": row["question"].strip(),
            "reference": row.get("reference"),
            "checks": checks,
        })
    return cases


async def main(spec: str, path: str):
    tenant_name, _, set_name = spec.partition("/")
    if not tenant_name or not set_name:
        sys.exit("Use tenant/set-name (e.g. atla-chatbot/facts-guard)")
    cases = parse_cases(Path(path).read_text(encoding="utf-8"))
    if not cases:
        sys.exit("The file has no cases")

    conn = await asyncpg.connect(DATABASE_URL)
    tid = await conn.fetchval("SELECT id FROM tenants WHERE name = $1", tenant_name)
    if tid is None:
        sys.exit(f"No tenant named '{tenant_name}'")
    set_id = await conn.fetchval(
        "INSERT INTO eval_sets (tenant_id, name, description) VALUES ($1, $2, $3) "
        "ON CONFLICT (tenant_id, name) DO UPDATE SET description = eval_sets.description RETURNING id",
        tid, set_name, "Hand-written guardrail cases",
    )
    added = 0
    for c in cases:
        result = await conn.execute(
            "INSERT INTO eval_cases (set_id, case_key, question, reference, checks, source) "
            "VALUES ($1, $2, $3, $4, $5::jsonb, $6) ON CONFLICT (set_id, case_key) DO NOTHING",
            set_id, c["case_key"], c["question"], c["reference"], json.dumps(c["checks"]), f"hand:{set_name}",
        )
        if result.endswith(" 1"):
            added += 1
    total = await conn.fetchval("SELECT count(*) FROM eval_cases WHERE set_id = $1", set_id)
    await conn.close()
    print(f"Set {tenant_name}/{set_name}: {added} added, {total} total")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python -m app.evalimport <tenant>/<set-name> <file.jsonl>")
    asyncio.run(main(sys.argv[1], sys.argv[2]))
