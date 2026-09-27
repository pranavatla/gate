import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app import db
from app.auth import Tenant, get_tenant
from app.ratelimit import charge_tokens, check_before_call
from app.ratelimit import client as redis_client
from app.router import route
from app.schemas import ChatRequest, ChatResponse

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("gate")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
    await db.disconnect()
    await redis_client.aclose()


app = FastAPI(title="gate.atla.in", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, tenant: Tenant = Depends(get_tenant)):
    await check_before_call(tenant)
    log.info("tenant=%s key=%s model=%s", tenant.name, tenant.key_prefix, req.model)

    resp = await route(req)

    await charge_tokens(tenant, resp.usage.input_tokens + resp.usage.output_tokens)
    return resp
