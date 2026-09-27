from dataclasses import dataclass

from fastapi import Header, HTTPException

from app import db
from app.keys import hash_key

@dataclass
class Tenant:
    id: int
    name: str
    key_prefix: str
    rpm_limit: int
    tpm_limit: int

async def get_tenant(authorization: str | None = Header(default=None)) -> Tenant:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing API key. Send 'Authorization: Bearer <key>'")

    key = authorization.removeprefix("Bearer ").strip()

    row = await db.pool.fetchrow(
        """
        SELECT t.id, t.name, k.key_prefix, t.rpm_limit, t.tpm_limit
        FROM api_keys k
        JOIN tenants t ON t.id = k.tenant_id
        WHERE k.key_hash = $1
          AND k.revoked_at IS NULL
          AND t.is_active
        """,
        hash_key(key),
    )

    if row is None:
        raise HTTPException(401, "Invalid or revoked API key")

    return Tenant(**dict(row))
