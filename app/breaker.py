import logging

from redis.exceptions import RedisError

from app.redis_conn import client

log = logging.getLogger("gate.breaker")

THRESHOLD = 3
WINDOW_S = 60
COOLDOWN_S = 30
MEMORY_S = 300


async def allow(provider: str) -> bool:
    try:
        if await client.exists(f"cb:{provider}:open"):
            return False
        if await client.exists(f"cb:{provider}:tripped"):
            return bool(await client.set(f"cb:{provider}:probe", 1, nx=True, ex=10))
        return True
    except RedisError:
        return True


async def is_open(provider: str) -> bool:
    """Read-only: True while the circuit is open. Unlike allow(), never takes a half-open probe slot."""
    try:
        return bool(await client.exists(f"cb:{provider}:open"))
    except RedisError:
        return False


async def record_success(provider: str):
    try:
        await client.delete(f"cb:{provider}:fails", f"cb:{provider}:tripped", f"cb:{provider}:probe")
    except RedisError:
        pass


async def record_failure(provider: str, fatal: bool = False):
    try:
        fails = await client.incr(f"cb:{provider}:fails")
        await client.expire(f"cb:{provider}:fails", WINDOW_S)
        half_open = await client.exists(f"cb:{provider}:tripped")

        if fatal or half_open or fails >= THRESHOLD:
            cooldown = COOLDOWN_S * 10 if fatal else COOLDOWN_S
            await client.set(f"cb:{provider}:open", 1, ex=cooldown)
            await client.set(f"cb:{provider}:tripped", 1, ex=MEMORY_S)
            await client.delete(f"cb:{provider}:probe")
            log.warning("circuit OPEN for %s (fails=%s fatal=%s, %ss)", provider, fails, fatal, cooldown)
    except RedisError:
        pass
