from app.config import ANTHROPIC_API_KEY
from app.providers.http import post_json
from app.schemas import ChatRequest, ChatResponse, ToolCall, Usage

URL = "https://api.anthropic.com/v1/messages"

STOP_REASONS = {
    "end_turn": "end",
    "stop_sequence": "end",
    "max_tokens": "max_tokens",
    "tool_use": "tool_use",
    "refusal": "filtered",
}


def _message(m) -> dict:
    if m.role == "tool":
        return {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}],
        }
    if m.role == "assistant" and m.tool_calls:
        blocks = [{"type": "text", "text": m.content}] if m.content else []
        blocks += [
            {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
            for c in m.tool_calls
        ]
        return {"role": "assistant", "content": blocks}
    return {"role": m.role, "content": m.content}


async def complete(req: ChatRequest, model: str) -> ChatResponse:
    payload = {
        "model": model,
        "max_tokens": req.max_tokens,
        "messages": [_message(m) for m in req.messages],
    }
    if req.system:
        payload["system"] = req.system
    if req.tools:
        payload["tools"] = [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in req.tools
        ]

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    data = await post_json("anthropic", URL, payload, headers)
    text = "".join(b["text"] for b in data["content"] if b["type"] == "text")
    calls = [
        ToolCall(id=b["id"], name=b["name"], arguments=b.get("input") or {})
        for b in data["content"]
        if b["type"] == "tool_use"
    ]

    return ChatResponse(
        provider="anthropic",
        model=data.get("model", model),
        content=text,
        usage=Usage(
            input_tokens=data["usage"]["input_tokens"],
            output_tokens=data["usage"]["output_tokens"],
        ),
        stop_reason=STOP_REASONS.get(data.get("stop_reason"), "other"),
        tool_calls=calls,
    )