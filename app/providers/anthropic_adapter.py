import httpx
from fastapi import HTTPException

from app.config import ANTHROPIC_API_KEY
from app.schemas import ChatRequest, ChatResponse, Usage

URL = "https://api.anthropic.com/v1/messages"


async def complete(req: ChatRequest, model: str) -> ChatResponse:
    payload = {
        "model": model,
        "max_tokens": req.max_tokens,
        "messages": [m.model_dump() for m in req.messages],
    }
    if req.system:
        payload["system"] = req.system

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(URL, json=payload, headers=headers)

    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    data = r.json()
    text = "".join(b["text"] for b in data["content"] if b["type"] == "text")

    return ChatResponse(
        provider="anthropic",
        model=data.get("model", model),
        content=text,
        usage=Usage(
            input_tokens=data["usage"]["input_tokens"],
            output_tokens=data["usage"]["output_tokens"],
        ),
    )
