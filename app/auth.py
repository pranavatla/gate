import json
from dataclasses import dataclass
from decimal import Decimal

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
    monthly_budget_usd: Decimal
    soft_limit_pct: int
    downgrade_model: str | None
    policy: dict
    agent_id: int | None
    agent_name: str | None
    agent_policy: dict | None


def _json_dict(value) -> dict | None:
    if value is None or isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _tenant_from_row(row) -> Tenant:
    data = dict(row)
    data["policy"] = _json_dict(data.get("policy")) or {}
    data["agent_policy"] = _json_dict(data.get("agent_policy"))
    return Tenant(**data)


async def get_tenant(authorization: str | None = Header(default=None)) -> Tenant:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing API key. Send 'Authorization: Bearer <key>'")

    key = authorization.removeprefix("Bearer ").strip()

    row = await db.pool.fetchrow(
        """
        SELECT t.id, t.name, k.key_prefix, t.rpm_limit, t.tpm_limit,
               t.monthly_budget_usd, t.soft_limit_pct, t.downgrade_model, t.policy,
               a.id AS agent_id, a.name AS agent_name, a.policy AS agent_policy
        FROM api_keys k
        JOIN tenants t ON t.id = k.tenant_id
        LEFT JOIN agents a ON a.id = k.agent_id
        WHERE k.key_hash = $1
          AND k.revoked_at IS NULL
          AND t.is_active
          AND (a.id IS NULL OR a.is_active)
        """,
        hash_key(key),
    )

    if row is None:
        raise HTTPException(401, "Invalid or revoked API key")

    return _tenant_from_row(row)

async def get_internal_tenant(name: str, key_prefix: str = "internal") -> Tenant:
    row = await db.pool.fetchrow(
        """
        SELECT t.id, t.name, $2::text AS key_prefix, t.rpm_limit, t.tpm_limit,
               t.monthly_budget_usd, t.soft_limit_pct, t.downgrade_model, t.policy,
               NULL::integer AS agent_id, NULL::text AS agent_name, NULL::jsonb AS agent_policy
        FROM tenants t
        WHERE t.name = $1
          AND t.is_active
        """,
        name, key_prefix,
    )
    if row is None:
        raise HTTPException(503, f"Tenant '{name}' is not configured")
    return _tenant_from_row(row)
