from urllib.parse import quote

from fastapi import HTTPException

from app.config import BEDROCK_API_KEY, BEDROCK_REGION
from app.providers.http import post_json
from app.schemas import ChatRequest, ChatResponse, Usage

STOP_REASONS = {
    "end_turn": "end",
    "stop_sequence": "end",
    "max_tokens": "max_tokens",
    "tool_use": "tool_use",
    "guardrail_intervened": "filtered",
    "content_filtered": "filtered",
}


async def complete(req: ChatRequest, model: str) -> ChatResponse:
    if not BEDROCK_API_KEY:
        raise HTTPException(503, "Bedrock is not configured on this gateway")

    payload = {
        "messages": [
            {"role": m.role, "content": [{"text": m.content}]}
            for m in req.messages
        ],
        "inferenceConfig": {"maxTokens": req.max_tokens},
    }
    if req.system:
        payload["system"] = [{"text": req.system}]
    if req.temperature is not None:
        payload["inferenceConfig"]["temperature"] = req.temperature

    url = (
        f"https://bedrock-runtime.{BEDROCK_REGION}.amazonaws.com"
        f"/model/{quote(model, safe='')}/converse"
    )
    headers = {
        "Authorization": f"Bearer {BEDROCK_API_KEY}",
        "content-type": "application/json",
    }

    data = await post_json("bedrock", url, payload, headers)
    blocks = data.get("output", {}).get("message", {}).get("content", [])
    text = "".join(b.get("text", "") for b in blocks)
    usage = data.get("usage", {})

    return ChatResponse(
        provider="bedrock",
        model=model,
        content=text,
        usage=Usage(
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
        ),
        stop_reason=STOP_REASONS.get(data.get("stopReason"), "other"),
    )
