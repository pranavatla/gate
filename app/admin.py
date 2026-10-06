import asyncio
import sys

import asyncpg
import re

from app.config import DATABASE_URL
from app.keys import AGENT_PREFIX, display_prefix, generate_key, hash_key
from pathlib import Path

async def create_tenant(name: str):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("INSERT INTO tenants (name) VALUES ($1)", name)
    await conn.close()
    print(f"Created tenant '{name}'")


async def issue_key(name: str):
    conn = await asyncpg.connect(DATABASE_URL)
    tenant_id = await conn.fetchval("SELECT id FROM tenants WHERE name = $1", name)
    if tenant_id is None:
        await conn.close()
        sys.exit(f"No tenant named '{name}'")

    key = generate_key()
    await conn.execute(
        "INSERT INTO api_keys (tenant_id, key_prefix, key_hash) VALUES ($1, $2, $3)",
        tenant_id, display_prefix(key), hash_key(key),
    )
    await conn.close()
    print(f"New key for '{name}'. It is shown ONCE, so store it now:\n{key}")


async def revoke_key(prefix: str):
    conn = await asyncpg.connect(DATABASE_URL)
    result = await conn.execute(
        "UPDATE api_keys SET revoked_at = now() WHERE key_prefix = $1 AND revoked_at IS NULL",
        prefix,
    )
    await conn.close()
    print(result)


async def create_agent(spec: str):
    tenant_name, _, agent_name = spec.partition("/")
    conn = await asyncpg.connect(DATABASE_URL)
    tenant_id = await conn.fetchval("SELECT id FROM tenants WHERE name = $1", tenant_name)
    if tenant_id is None or not agent_name:
        await conn.close()
        sys.exit("Use tenant/agent (e.g. gita/verse-finder) with an existing tenant")

    await conn.execute("INSERT INTO agents (tenant_id, name) VALUES ($1, $2)", tenant_id, agent_name)
    await conn.close()
    print(f"Created agent '{agent_name}' for tenant '{tenant_name}'")


async def issue_agent_key(spec: str):
    tenant_name, _, agent_name = spec.partition("/")
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow(
        """
        SELECT a.id, a.tenant_id
        FROM agents a JOIN tenants t ON t.id = a.tenant_id
        WHERE t.name = $1 AND a.name = $2
        """,
        tenant_name, agent_name,
    )
    if row is None:
        await conn.close()
        sys.exit(f"No agent '{spec}'")

    key = generate_key(AGENT_PREFIX)
    await conn.execute(
        "INSERT INTO api_keys (tenant_id, agent_id, key_prefix, key_hash) VALUES ($1, $2, $3, $4)",
        row["tenant_id"], row["id"], display_prefix(key), hash_key(key),
    )
    await conn.close()
    print(f"New key for agent '{spec}'. It is shown ONCE, so store it now:\n{key}")


NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _spec(spec: str) -> tuple[str, str]:
    tenant_name, _, name = spec.partition("/")
    if not name or not NAME_RE.match(name):
        sys.exit("Use tenant/prompt-name (e.g. gita/gita-answer); the name allows letters, digits, - and _")
    return tenant_name, name


async def _tenant_id(conn, tenant_name: str) -> int:
    tid = await conn.fetchval("SELECT id FROM tenants WHERE name = $1", tenant_name)
    if tid is None:
        await conn.close()
        sys.exit(f"No tenant named '{tenant_name}'")
    return tid


async def _require_version(conn, tid: int, name: str, version: int):
    ok = await conn.fetchval(
        "SELECT 1 FROM prompt_versions WHERE tenant_id=$1 AND name=$2 AND version=$3",
        tid, name, version,
    )
    if not ok:
        await conn.close()
        sys.exit(f"Prompt '{name}' has no version {version}")


async def publish_prompt(spec: str, path: str, note: str | None = None):
    tenant_name, name = _spec(spec)
    body = Path(path).read_text(encoding="utf-8").strip()
    if not body:
        sys.exit("The prompt file is empty")
    conn = await asyncpg.connect(DATABASE_URL)
    tid = await _tenant_id(conn, tenant_name)
    async with conn.transaction():
        version = await conn.fetchval(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM prompt_versions WHERE tenant_id=$1 AND name=$2",
            tid, name,
        )
        await conn.execute(
            "INSERT INTO prompt_versions (tenant_id, name, version, body, note) VALUES ($1,$2,$3,$4,$5)",
            tid, name, version, body, note,
        )
        made = await conn.execute(
            "INSERT INTO prompt_rollouts (tenant_id, name, stable_version) VALUES ($1,$2,$3) "
            "ON CONFLICT DO NOTHING",
            tid, name, version,
        )
    await conn.close()
    print(f"Published {tenant_name}/{name} v{version}")
    if made.endswith(" 1"):
        print("First version: it is now the stable version")
    else:
        print(f"Not live yet. Use: rollout-prompt {spec} {version} <pct>")


async def rollout_prompt(spec: str, version: str, pct: str):
    tenant_name, name = _spec(spec)
    version_i, pct_i = int(version), int(pct)
    if not 0 <= pct_i <= 100:
        sys.exit("pct must be between 0 and 100")
    conn = await asyncpg.connect(DATABASE_URL)
    tid = await _tenant_id(conn, tenant_name)
    await _require_version(conn, tid, name, version_i)
    stable = await conn.fetchval(
        "SELECT stable_version FROM prompt_rollouts WHERE tenant_id=$1 AND name=$2", tid, name
    )
    if stable is None:
        await conn.close()
        sys.exit(f"No rollout for '{spec}'. Publish a first version first")
    if stable == version_i:
        await conn.close()
        sys.exit(f"v{version_i} is already the stable version")
    await conn.execute(
        "UPDATE prompt_rollouts SET candidate_version=$3, candidate_pct=$4, updated_at=now() "
        "WHERE tenant_id=$1 AND name=$2",
        tid, name, version_i, pct_i,
    )
    await conn.close()
    print(f"{spec}: {pct_i}% of traffic now goes to v{version_i} (stable is v{stable}). "
          "Allow up to 15 seconds to take effect")


async def promote_prompt(spec: str):
    tenant_name, name = _spec(spec)
    conn = await asyncpg.connect(DATABASE_URL)
    tid = await _tenant_id(conn, tenant_name)
    row = await conn.fetchrow(
        "UPDATE prompt_rollouts SET stable_version=candidate_version, candidate_version=NULL, "
        "candidate_pct=0, updated_at=now() "
        "WHERE tenant_id=$1 AND name=$2 AND candidate_version IS NOT NULL "
        "RETURNING stable_version",
        tid, name,
    )
    await conn.close()
    if row is None:
        sys.exit(f"'{spec}' has no candidate to promote")
    print(f"{spec}: v{row['stable_version']} is now stable for 100% of traffic")


async def rollback_prompt(spec: str, version: str | None = None):
    tenant_name, name = _spec(spec)
    conn = await asyncpg.connect(DATABASE_URL)
    tid = await _tenant_id(conn, tenant_name)
    if version is not None:
        await _require_version(conn, tid, name, int(version))
        result = await conn.execute(
            "UPDATE prompt_rollouts SET stable_version=$3, candidate_version=NULL, "
            "candidate_pct=0, updated_at=now() WHERE tenant_id=$1 AND name=$2",
            tid, name, int(version),
        )
        msg = f"{spec}: stable is now v{version}, candidate cleared"
    else:
        result = await conn.execute(
            "UPDATE prompt_rollouts SET candidate_version=NULL, candidate_pct=0, updated_at=now() "
            "WHERE tenant_id=$1 AND name=$2",
            tid, name,
        )
        msg = f"{spec}: candidate cleared, 100% back on the stable version"
    await conn.close()
    if result.endswith(" 0"):
        sys.exit(f"No rollout for '{spec}'")
    print(msg)


async def show_prompt(spec: str):
    tenant_name, name = _spec(spec)
    conn = await asyncpg.connect(DATABASE_URL)
    tid = await _tenant_id(conn, tenant_name)
    rollout = await conn.fetchrow(
        "SELECT * FROM prompt_rollouts WHERE tenant_id=$1 AND name=$2", tid, name
    )
    versions = await conn.fetch(
        "SELECT version, created_at, note, left(body, 60) AS preview FROM prompt_versions "
        "WHERE tenant_id=$1 AND name=$2 ORDER BY version", tid, name,
    )
    await conn.close()
    if not versions:
        sys.exit(f"No prompt '{spec}'")
    if rollout:
        print(f"stable=v{rollout['stable_version']} candidate={rollout['candidate_version']} "
              f"candidate_pct={rollout['candidate_pct']}%")
    for v in versions:
        print(f"v{v['version']}  {v['created_at']:%Y-%m-%d %H:%M}  {v['note'] or ''}  | {v['preview']!r}")

async def _scope_id(conn, scope: str) -> int | None:
    """'global' means every tenant; anything else is a tenant name."""
    return None if scope == "global" else await _tenant_id(conn, scope)


async def set_flag(flag: str, scope: str, state: str, pct: str = "100"):
    if not NAME_RE.match(flag):
        sys.exit("Flag names allow letters, digits, - and _ (max 64)")
    if state not in ("on", "off"):
        sys.exit("State must be 'on' or 'off'")
    pct_i = int(pct)
    if not 0 <= pct_i <= 100:
        sys.exit("pct must be between 0 and 100")
    conn = await asyncpg.connect(DATABASE_URL)
    tid = await _scope_id(conn, scope)
    async with conn.transaction():
        await conn.execute(
            "DELETE FROM feature_flags WHERE flag = $1 AND tenant_id IS NOT DISTINCT FROM $2::integer",
            flag, tid,
        )
        await conn.execute(
            "INSERT INTO feature_flags (flag, tenant_id, enabled, rollout_pct) VALUES ($1, $2, $3, $4)",
            flag, tid, state == "on", pct_i,
        )
    await conn.close()
    print(f"{flag} for {scope}: {state}" + (f" at {pct_i}%" if state == "on" and pct_i < 100 else "")
          + ". Allow up to 15 seconds to take effect")


async def clear_flag(flag: str, scope: str):
    conn = await asyncpg.connect(DATABASE_URL)
    tid = await _scope_id(conn, scope)
    result = await conn.execute(
        "DELETE FROM feature_flags WHERE flag = $1 AND tenant_id IS NOT DISTINCT FROM $2::integer",
        flag, tid,
    )
    await conn.close()
    print(f"{flag} for {scope}: " + ("cleared" if result.endswith(" 1") else "nothing to clear"))


async def show_flags(_: str = "all"):
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch(
        "SELECT f.flag, COALESCE(t.name, 'global') AS scope, f.enabled, f.rollout_pct "
        "FROM feature_flags f LEFT JOIN tenants t ON t.id = f.tenant_id "
        "ORDER BY f.flag, f.tenant_id NULLS FIRST"
    )
    await conn.close()
    if not rows:
        print("No flags set")
    for r in rows:
        state = "on" if r["enabled"] else "off"
        print(f"{r['flag']:<24} {r['scope']:<24} {state}  {r['rollout_pct']}%")

COMMANDS = {
    "create-tenant": create_tenant,
    "issue-key": issue_key,
    "revoke-key": revoke_key,
    "create-agent": create_agent,
    "issue-agent-key": issue_agent_key,
    "publish-prompt": publish_prompt,
    "rollout-prompt": rollout_prompt,
    "promote-prompt": promote_prompt,
    "rollback-prompt": rollback_prompt,
    "show-prompt": show_prompt,
    "set-flag": set_flag,
    "clear-flag": clear_flag,
    "show-flags": show_flags,
}

if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in COMMANDS:
        sys.exit(f"Usage: python -m app.admin [{'|'.join(COMMANDS)}] <value> [more values]")
    asyncio.run(COMMANDS[sys.argv[1]](*sys.argv[2:]))