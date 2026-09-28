import logging
from dataclasses import dataclass

from fastapi import HTTPException

from app import breaker, db
from app.agents import uses_tools
from app.providers.http import ProviderError
from app.router import route
from app.schemas import ChatRequest, ChatResponse

log = logging.getLogger("gate.failover")

TOOL_CAPABLE = {"anthropic", "openai"}

CHAIN_SQL = """
SELECT fallback_model FROM fallback_routes
WHERE primary_model = $1
ORDER BY priority
"""


@dataclass
class Outcome:
    response: ChatResponse
    model: str


async def chain_for(model: str) -> list[str]:
    rows = await db.pool.fetch(CHAIN_SQL, model)
    return [model] + [r["fallback_model"] for r in rows]


async def call_with_failover(
    req: ChatRequest, attempted: list[str], allowed: set[str] | None = None
) -> Outcome:
    last_error = None
    needs_tools = uses_tools(req)

    for model in await chain_for(req.model):
        provider = model.partition("/")[0]

        if allowed is not None and model not in allowed:
            attempted.append(f"denied:{model}")
            continue

        if needs_tools and provider not in TOOL_CAPABLE:
            attempted.append(f"unsupported:{model}")
            continue

        if not await breaker.allow(provider):
            attempted.append(f"skipped:{model}")
            continue

        attempted.append(model)
        try:
            resp = await route(req.model_copy(update={"model": model}))
        except ProviderError as e:
            if not e.failover:
                raise HTTPException(e.status, e.detail)
            await breaker.record_failure(provider, fatal=e.fatal)
            log.warning("failover: %s failed (%s %s), trying next", model, e.status, e.detail[:100])
            last_error = e
            continue

        await breaker.record_success(provider)
        return Outcome(resp, model)

    if last_error:
        raise HTTPException(503, f"All providers failed. Last error: {last_error}")
    raise HTTPException(503, "No capable, healthy provider available")