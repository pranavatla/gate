import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app import db
from app.auth import Tenant, get_tenant
from app.router import route
from app.schemas import ChatRequest, ChatResponse

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("gate")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
    await db.disconnect()


app = FastAPI(title="gate.atla.in", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, tenant: Tenant = Depends(get_tenant)):
    log.info("tenant=%s key=%s model=%s", tenant.name, tenant.key_prefix, req.model)
    return await route(req)