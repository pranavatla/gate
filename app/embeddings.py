from app.config import OPENAI_API_KEY
from app.providers.http import post_json

URL = "https://api.openai.com/v1/embeddings"
MODEL = "text-embedding-3-small"
CATALOG_NAME = f"openai/{MODEL}"


async def embed(text: str) -> tuple[list[float], int]:
    data = await post_json(
        "openai",
        URL,
        {"model": MODEL, "input": text},
        {"Authorization": f"Bearer {OPENAI_API_KEY}", "content-type": "application/json"},
    )
    return data["data"][0]["embedding"], data["usage"]["prompt_tokens"]
