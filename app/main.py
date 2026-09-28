import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Response

from app import db
from app.audit import UsageEvent, record
from app.auth import Tenant, get_tenant
from app.budget import cost_usd, decide, price_of
from app.failover import call_with_failover
from app.providers import http as provider_http
from app.ratelimit import charge_tokens, check_before_call
from app.redis_conn import client as redis_client
from app.schemas import ChatRequest, ChatResponse

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


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, response: Response, tenant: Tenant = Depends(get_tenant)):
    request_id = uuid.uuid4()
    response.headers["X-Request-ID"] = str(request_id)
    started = time.perf_counter()
    attempted: list[str] = []

    ev = UsageEvent(
        request_id=request_id,
        tenant_id=tenant.id,
        key_prefix=tenant.key_prefix,
        requested_model=req.model,
        provider=req.model.partition("/")[0],
    )
    stage = "limits"

    try:
        await check_before_call(tenant)

        stage = "budget"
        decision = await decide(tenant, req)
        response.headers["X-Gate-Downgraded"] = str(decision.downgraded).lower()
        response.headers["X-Gate-Budget-Used-Pct"] = str(decision.used_pct)

        stage = "provider"
        outcome = await call_with_failover(
            req.model_copy(update={"model": decision.model}), attempted
        )
        resp = outcome.response

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
        ev.cost_usd = cost_usd(await price_of(outcome.model), ev.input_tokens, ev.output_tokens)
        return resp

    except HTTPException as e:
        if stage == "limits":
            ev.status = "rate_limited"
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
        log.info(
            "req=%s tenant=%s model=%s routed=%s attempts=%s status=%s ms=%s cost=%s",
            request_id, tenant.name, req.model, ev.routed_model, attempted,
            ev.status, ev.latency_ms, ev.cost_usd,
        )
        await record(ev)