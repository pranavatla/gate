from app.config import GEMINI_API_KEY
from app.providers.http import post_json
from app.schemas import ChatRequest, ChatResponse, Usage

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


async def complete(req: ChatRequest, model: str) -> ChatResponse:
    contents = [
        {
            "role": "model" if m.role == "assistant" else "user",
            "parts": [{"text": m.content}],
        }
        for m in req.messages
    ]

    payload = {
        "contents": contents,
        "generationConfig": {"maxOutputTokens": req.max_tokens},
    }
    if req.system:
        payload["systemInstruction"] = {"parts": [{"text": req.system}]}

    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "content-type": "application/json",
    }

    data = await post_json("gemini", f"{BASE_URL}/{model}:generateContent", payload, headers)
    candidate = data.get("candidates", [{}])[0]
    parts = candidate.get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts)
    meta = data.get("usageMetadata", {})

    return ChatResponse(
        provider="gemini",
        model=data.get("modelVersion", model),
        content=text,
        usage=Usage(
            input_tokens=meta.get("promptTokenCount", 0),
            output_tokens=meta.get("candidatesTokenCount", 0) + meta.get("thoughtsTokenCount", 0),
        ),
    )