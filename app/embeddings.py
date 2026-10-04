from app.tracing import traced, usage
from app.budget import price_of, cost_usd
from app.config import OPENAI_API_KEY
from app.providers.http import post_json

URL = "https://api.openai.com/v1/embeddings"
MODEL = "text-embedding-3-small"
CATALOG_NAME = f"openai/{MODEL}"


@traced("gate.embedding", "embedding")
async def embed(text: str) -> tuple[list[float], int]:
    data = await post_json(
        "openai",
        URL,
        {"model": MODEL, "input": text},
        {"Authorization": f"Bearer {OPENAI_API_KEY}", "content-type": "application/json"},
    )
    tokens = data["usage"]["prompt_tokens"]
    try:
        price = await price_of(CATALOG_NAME)
        usage(CATALOG_NAME, tokens, 0, cost_usd(price, tokens, 0), 0)
    except Exception:
        usage(CATALOG_NAME, tokens)
    return data["data"][0]["embedding"], data["usage"]["prompt_tokens"]
