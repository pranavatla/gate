import asyncio
import sys

import asyncpg

from app.config import DATABASE_URL
from app.keys import AGENT_PREFIX, display_prefix, generate_key, hash_key


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


COMMANDS = {
    "create-tenant": create_tenant,
    "issue-key": issue_key,
    "revoke-key": revoke_key,
    "create-agent": create_agent,
    "issue-agent-key": issue_agent_key,
}

if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in COMMANDS:
        sys.exit(f"Usage: python -m app.admin [{'|'.join(COMMANDS)}] <value>")
    asyncio.run(COMMANDS[sys.argv[1]](sys.argv[2]))