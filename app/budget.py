from dataclasses import dataclass
from decimal import Decimal

from fastapi import HTTPException

from app import db
from app.schemas import ChatRequest

PRICE_SQL = """
SELECT input_per_mtok, output_per_mtok
FROM model_prices
WHERE provider = $1 AND model = $2 AND effective_from <= now()
ORDER BY effective_from DESC
LIMIT 1
"""

SPENT_SQL = """
SELECT COALESCE(SUM(cost_usd), 0)
FROM usage_events
WHERE tenant_id = $1 AND created_at >= date_trunc('month', now())
"""


@dataclass
class BudgetDecision:
    model: str
    downgraded: bool
    used_pct: int


async def price_of(full_model: str):
    provider, _, model = full_model.partition("/")
    row = await db.pool.fetchrow(PRICE_SQL, provider, model)
    if row is None:
        raise HTTPException(400, f"Model '{full_model}' is not in the gateway catalog")
    return row


async def decide(tenant, req: ChatRequest) -> BudgetDecision:
    await price_of(req.model)
    spent = await db.pool.fetchval(SPENT_SQL, tenant.id)
    budget = tenant.monthly_budget_usd

    if spent >= budget:
        raise HTTPException(
            402, f"Monthly budget of ${budget:.4f} exhausted (spent ${spent:.4f})"
        )

    used_pct = int(spent / budget * 100)

    if (
        used_pct >= tenant.soft_limit_pct
        and tenant.downgrade_model
        and req.model != tenant.downgrade_model
    ):
        await price_of(tenant.downgrade_model)
        return BudgetDecision(tenant.downgrade_model, True, used_pct)

    return BudgetDecision(req.model, False, used_pct)


def cost_usd(price, input_tokens: int, output_tokens: int) -> Decimal:
    return (
        input_tokens * price["input_per_mtok"] + output_tokens * price["output_per_mtok"]
    ) / 1_000_000