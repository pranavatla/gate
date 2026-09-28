import httpx
from redis.exceptions import RedisError

from app.config import CHAOS_ENABLED
from app.redis_conn import client as redis_client

TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
_http = httpx.AsyncClient(timeout=TIMEOUT)

FAILOVER_STATUSES = {408, 429, 500, 502, 503, 504, 529}


class ProviderError(Exception):
    def __init__(self, provider: str, status: int, detail: str):
        super().__init__(f"{provider} {status}: {detail[:200]}")
        self.provider = provider
        self.status = status
        self.detail = detail
        low = detail.lower()
        self.fatal = (
            status in (401, 403)
            or "insufficient_quota" in low
            or "credit_balance" in low
            or "credit balance" in low
        )
        self.failover = self.fatal or status in FAILOVER_STATUSES


async def _chaos(provider: str) -> bool:
    if not CHAOS_ENABLED:
        return False
    try:
        return bool(await redis_client.exists(f"chaos:{provider}"))
    except RedisError:
        return False


async def post_json(provider: str, url: str, payload: dict, headers: dict) -> dict:
    if await _chaos(provider):
        raise ProviderError(provider, 503, "chaos: injected failure")

    try:
        r = await _http.post(url, json=payload, headers=headers)
    except httpx.TimeoutException:
        raise ProviderError(provider, 504, "timeout")
    except httpx.TransportError as e:
        raise ProviderError(provider, 502, f"connection error: {e}")

    if r.status_code >= 400:
        raise ProviderError(provider, r.status_code, r.text)

    return r.json()


async def close():
    await _http.aclose()
