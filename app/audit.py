import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal

from app import db

log = logging.getLogger("gate.audit")


@dataclass(slots=True)
class UsageEvent:
    request_id: uuid.UUID
    tenant_id: int
    key_prefix: str
    requested_model: str
    provider: str
    status: str = "failed"
    http_status: int = 500
    resolved_model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    error: str | None = None
    routed_model: str | None = None
    cost_usd: Decimal | None = None
    attempted_models: list[str] | None = None
    policy_actions: list[str] | None = None


INSERT = """
INSERT INTO usage_events
    (request_id, tenant_id, key_prefix, requested_model, provider, resolved_model,
     status, http_status, input_tokens, output_tokens, latency_ms, error,
     routed_model, cost_usd, attempted_models, policy_actions)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
"""


async def record(e: UsageEvent):
    try:
        await db.pool.execute(
            INSERT,
            e.request_id, e.tenant_id, e.key_prefix, e.requested_model, e.provider,
            e.resolved_model, e.status, e.http_status, e.input_tokens,
            e.output_tokens, e.latency_ms, e.error, e.routed_model, e.cost_usd,
            e.attempted_models, e.policy_actions,
        )
    except Exception:
        log.exception("audit write failed for request %s", e.request_id)