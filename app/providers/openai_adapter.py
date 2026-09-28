import json

from app.config import OPENAI_API_KEY
from app.providers.http import post_json
from app.schemas import ChatRequest, ChatResponse, ToolCall, Usage

URL = "https://api.openai.com/v1/chat/completions"

STOP_REASONS = {
    "stop": "end",
    "length": "max_tokens",
    "tool_calls": "tool_use",
    "content_filter": "filtered",
}


def _message(m) -> dict:
    if m.role == "tool":
        return {"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content}
    if m.role == "assistant" and m.tool_calls:
        return {
            "role": "assistant",
            "content": m.content or None,
            "tool_calls": [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                }
                for c in m.tool_calls
            ],
        }
    return {"role": m.role, "content": m.content}


def _arguments(raw: str | None) -> dict:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"_unparsed": raw}


async def complete(req: ChatRequest, model: str) -> ChatResponse:
    messages = []
    if req.system:
        messages.append({"role": "system", "content": req.system})
    messages += [_message(m) for m in req.messages]

    payload = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": req.max_tokens,
    }
    if req.tools:
        payload["tools"] = [
            {
                "type": "function",
                "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
            }
            for t in req.tools
        ]

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "content-type": "application/json",
    }

    data = await post_json("openai", URL, payload, headers)
    choice = data["choices"][0]
    msg = choice["message"]
    calls = [
        ToolCall(id=c["id"], name=c["function"]["name"], arguments=_arguments(c["function"].get("arguments")))
        for c in msg.get("tool_calls") or []
    ]

    return ChatResponse(
        provider="openai",
        model=data.get("model", model),
        content=msg.get("content") or "",
        usage=Usage(
            input_tokens=data["usage"]["prompt_tokens"],
            output_tokens=data["usage"]["completion_tokens"],
        ),
        stop_reason=STOP_REASONS.get(choice.get("finish_reason"), "other"),
        tool_calls=calls,
    )