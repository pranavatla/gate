"""Per-visitor limits for the public /v1/landing-chat endpoint.

The tenant's own RPM/TPM/budget limits are shared by every visitor, so on their own one person could use
them all up. These counters are per visitor, so one person can only exhaust their own allowance.
Visitors are identified by a truncated SHA-256 of the client IP; the raw IP is never stored.
"""
import hashlib
import logging
import time

from fastapi import HTTPException, Request
from redis.exceptions import RedisError

from app.config import RATELIMIT_FAIL_OPEN
from app.redis_conn import client

log = logging.getLogger("gate.visitor")

# (window seconds, max requests in the window, label)
WINDOWS = ((60, 6, "minute"), (86400, 60, "day"))


def visitor_id(request: Request) -> str:
    # Caddy sets X-Forwarded-For to the real client address; the last entry is the one our proxy added.
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[-1].strip() if forwarded else (request.client.host if request.client else "unknown")
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


async def check_visitor(request: Request) -> None:
    vid = visitor_id(request)
    now = int(time.time())
    try:
        for seconds, limit, label in WINDOWS:
            key = f"vl:{vid}:{label}:{now // seconds}"
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.expire(key, seconds)
            count = (await pipe.execute())[0]
            if count > limit:
                retry = seconds - (now % seconds)
                raise HTTPException(
                    status_code=429,
                    detail=f"You are asking too quickly: limit is {limit} questions per {label}. Try again in {retry}s.",
                    headers={"Retry-After": str(retry)},
                )
    except RedisError as e:
        log.warning("visitor limit unavailable: %s", e)
        if not RATELIMIT_FAIL_OPEN:
            raise HTTPException(503, "Rate limiter unavailable")
