import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import ANTHROPIC_API_KEY

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

app = FastAPI(title="gate.atla.in")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/anthropic/messages")
async def proxy_anthropic(request: Request):
    body = await request.json()

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        upstream = await client.post(ANTHROPIC_URL, json=body, headers=headers)

    return JSONResponse(status_code=upstream.status_code, content=upstream.json())
