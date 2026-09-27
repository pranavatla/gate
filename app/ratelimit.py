from pathlib import Path

import redis.asyncio as redis
from fastapi import HTTPException

from app.config import REDIS_URL

client = redis.from_url(REDIS_URL, decode_responses=True)
_script = client.register_script(Path(__file__).with_name("token_bucket.lua").read_text())


async def _take(key: str, limit_per_min: int, need: int, cost: int, force: int = 0):
    allowed, remaining, retry_ms = await _script(
        keys=[key],
        args=[limit_per_min, limit_per_min / 60, need, cost, force],
    )
    return allowed == 1, remaining, retry_ms


def _limited(what: str, retry_ms: int):
    retry_s = max(1, -(-retry_ms // 1000))
    raise HTTPException(
        status_code=429,
        detail=f"Rate limit exceeded: {what}. Retry after {retry_s}s",
        headers={"Retry-After": str(retry_s)},
    )


async def check_before_call(tenant):
    ok, _, retry_ms = await _take(f"rl:{tenant.id}:tok", tenant.tpm_limit, need=1, cost=0)
    if not ok:
        _limited("tokens per minute", retry_ms)

    ok, _, retry_ms = await _take(f"rl:{tenant.id}:req", tenant.rpm_limit, need=1, cost=1)
    if not ok:
        _limited("requests per minute", retry_ms)


async def charge_tokens(tenant, used: int):
    await _take(f"rl:{tenant.id}:tok", tenant.tpm_limit, need=0, cost=used, force=1)
