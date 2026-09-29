from fastapi import HTTPException

from app.providers import anthropic_adapter, bedrock_adapter, gemini_adapter, openai_adapter
from app.schemas import ChatRequest, ChatResponse

ADAPTERS = {
    "anthropic": anthropic_adapter.complete,
    "openai": openai_adapter.complete,
    "gemini": gemini_adapter.complete,
    "bedrock": bedrock_adapter.complete,
}


async def route(req: ChatRequest) -> ChatResponse:
    provider, sep, model = req.model.partition("/")
    if not sep or not model:
        raise HTTPException(400, "model must look like 'provider/model-id'")

    adapter = ADAPTERS.get(provider)
    if adapter is None:
        raise HTTPException(
            400, f"Unknown provider '{provider}'. Use one of: {', '.join(ADAPTERS)}"
        )

    return await adapter(req, model)