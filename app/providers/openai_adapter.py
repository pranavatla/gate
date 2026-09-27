import httpx
from fastapi import HTTPException

from app.config import OPENAI_API_KEY
from app.schemas import ChatRequest, ChatResponse, Usage

URL = "https://api.openai.com/v1/chat/completions"


async def complete(req: ChatRequest, model: str) -> ChatResponse:
    messages = []
    if req.system:
        messages.append({"role": "system", "content": req.system})
    messages += [m.model_dump() for m in req.messages]

    payload = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": req.max_tokens,
    }

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(URL, json=payload, headers=headers)

    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    data = r.json()
    text = data["choices"][0]["message"].get("content") or ""

    return ChatResponse(
        provider="openai",
        model=data.get("model", model),
        content=text,
        usage=Usage(
            input_tokens=data["usage"]["prompt_tokens"],
            output_tokens=data["usage"]["completion_tokens"],
        ),
    )
