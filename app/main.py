import logging
import time
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import Depends, FastAPI, Header, HTTPException, Response

from app import cache, db
from app.agents import add_run_cost, check_tools, review_tool_calls, start_step
from app.audit import UsageEvent, record
from app.auth import Tenant, get_tenant
from app.budget import cost_usd, decide, price_of
from app.embeddings import CATALOG_NAME as EMBED_MODEL
from app.failover import call_with_failover
from app.policy import apply_policy
from app.providers import http as provider_http
from app.ratelimit import charge_tokens, check_before_call
from app.redis_conn import client as redis_client
from app.schemas import ChatRequest, ChatResponse, Usage

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("gate")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
    await db.disconnect()
    await provider_http.close()
    await redis_client.aclose()


app = FastAPI(title="gate.atla.in", lifespan=lifespan)


async def embedding_cost(tokens: int) -> Decimal:
    if not tokens:
        return Decimal(0)
    return cost_usd(await price_of(EMBED_MODEL), tokens, 0)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    response: Response,
    tenant: Tenant = Depends(get_tenant),
    x_agent_run_id: str | None = Header(default=None),
):
    request_id = uuid.uuid4()
    response.headers["X-Request-ID"] = str(request_id)
    started = time.perf_counter()
    attempted: list[str] = []
    policy_actions: list[str] = []

    ev = UsageEvent(
        request_id=request_id,
        tenant_id=tenant.id,
        key_prefix=tenant.key_prefix,
        requested_model=req.model,
        provider=req.model.partition("/")[0],
        agent_id=tenant.agent_id,
        run_id=x_agent_run_id,
    )
    stage = "limits"

    try:
        await check_before_call(tenant)

        stage = "policy"
        pol = apply_policy(tenant, req, policy_actions)
        check_tools(tenant, pol.request, policy_actions)
        await start_step(tenant, x_agent_run_id, policy_actions)

        stage = "cache"
        t0 = time.perf_counter()
        cached = await cache.lookup(tenant, pol.request)
        log.info("timing cache_lookup_ms=%d", (time.perf_counter() - t0) * 1000)
        ev.cache_status = cached.status
        response.headers["X-Gate-Cache"] = cached.status
        if cached.similarity is not None:
            response.headers["X-Gate-Cache-Similarity"] = f"{cached.similarity:.4f}"
        embed_cost = await embedding_cost(cached.embed_tokens)

        if cached.status == "hit":
            ev.status = "ok"
            ev.http_status = 200
            ev.provider = "cache"
            ev.routed_model = "cache"
            ev.resolved_model = cached.response.model
            ev.stop_reason = cached.response.stop_reason
            ev.cost_usd = embed_cost
            if policy_actions:
                response.headers["X-Gate-Policy"] = ",".join(policy_actions)
            return cached.response.model_copy(
                update={"usage": Usage(input_tokens=0, output_tokens=0)}
            )

        stage = "budget"
        decision = await decide(tenant, pol.request)
        response.headers["X-Gate-Downgraded"] = str(decision.downgraded).lower()
        response.headers["X-Gate-Budget-Used-Pct"] = str(decision.used_pct)

        stage = "provider"
        t0 = time.perf_counter()
        outcome = await call_with_failover(
            pol.request.model_copy(update={"model": decision.model}),
            attempted,
            pol.allowed_models,
        )
        resp = outcome.response
        ev.provider_ms = int((time.perf_counter() - t0) * 1000)
        log.info("timing provider_ms=%d", ev.provider_ms)

        review_tool_calls(tenant, pol.request, resp, policy_actions)

        ev.routed_model = outcome.model
        ev.provider = outcome.model.partition("/")[0]
        response.headers["X-Gate-Routed-Model"] = outcome.model
        response.headers["X-Gate-Fallback"] = str(outcome.model != decision.model).lower()

        await charge_tokens(tenant, resp.usage.input_tokens + resp.usage.output_tokens)

        ev.status = "ok"
        ev.http_status = 200
        ev.resolved_model = resp.model
        ev.input_tokens = resp.usage.input_tokens
        ev.output_tokens = resp.usage.output_tokens
        ev.stop_reason = resp.stop_reason
        ev.tool_calls = [c.name for c in resp.tool_calls] or None
        ev.cost_usd = (
            cost_usd(await price_of(outcome.model), ev.input_tokens, ev.output_tokens)
            + embed_cost
        )
        await add_run_cost(tenant, x_agent_run_id, ev.cost_usd)

        if outcome.model == pol.request.model:
            t0 = time.perf_counter()
            await cache.store(tenant, pol.request, cached, resp)
            log.info("timing cache_store_ms=%d", (time.perf_counter() - t0) * 1000)

        if policy_actions:
            response.headers["X-Gate-Policy"] = ",".join(policy_actions)
        return resp

    except HTTPException as e:
        if stage == "limits":
            ev.status = "rate_limited"
        elif stage == "policy":
            ev.status = "over_budget" if e.status_code == 402 else "blocked"
        elif stage == "budget":
            ev.status = "over_budget" if e.status_code == 402 else "rejected"
        else:
            ev.status = "failed"
        ev.http_status = e.status_code
        ev.error = str(e.detail)[:500]
        e.headers = {**(e.headers or {}), "X-Request-ID": str(request_id)}
        raise

    finally:
        ev.latency_ms = int((time.perf_counter() - started) * 1000)
        ev.attempted_models = attempted or None
        ev.policy_actions = policy_actions or None
        log.info(
            "req=%s tenant=%s agent=%s run=%s model=%s routed=%s cache=%s attempts=%s "
            "policy=%s tools=%s stop=%s status=%s ms=%s cost=%s",
            request_id, tenant.name, tenant.agent_name, x_agent_run_id, req.model,
            ev.routed_model, ev.cache_status, attempted, policy_actions, ev.tool_calls,
            ev.stop_reason, ev.status, ev.latency_ms, ev.cost_usd,
        )
        await record(ev)