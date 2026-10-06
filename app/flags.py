"""Feature flags.

A flag is a named on/off switch with an optional percentage. A row with a
tenant_id applies to that tenant only; a row with no tenant (global) is the
default for everyone. The tenant row wins over the global row. If a flag is
not set anywhere, it is off. Flag lookups never break a chat request: any
database problem falls back to the last known values, then to "off".
"""
import logging
import time

from app import db
from app.prompts import bucket

log = logging.getLogger("gate.flags")

CACHE_TTL_S = 15  # a flag change can take up to this long to be seen
_cache: dict[int, tuple[float, dict[str, tuple[bool, int]]]] = {}

LOAD = """
SELECT flag, tenant_id, enabled, rollout_pct
FROM feature_flags
WHERE tenant_id = $1 OR tenant_id IS NULL
"""


def merge(rows) -> dict[str, tuple[bool, int]]:
    """Global rows first, then tenant rows on top, so the tenant row wins."""
    merged: dict[str, tuple[bool, int]] = {}
    for r in sorted(rows, key=lambda r: r["tenant_id"] is not None):
        merged[r["flag"]] = (r["enabled"], r["rollout_pct"])
    return merged


def decide(flags: dict[str, tuple[bool, int]], tenant_id: int, flag: str, key: str,
           default: bool = False) -> bool:
    """Pure decision logic, no database. Easy to unit test."""
    if flag not in flags:
        return default
    enabled, pct = flags[flag]
    if not enabled:
        return False
    return pct >= 100 or bucket(tenant_id, flag, key) < pct


async def _load(tenant_id: int) -> dict[str, tuple[bool, int]]:
    now = time.monotonic()
    hit = _cache.get(tenant_id)
    if hit and now - hit[0] < CACHE_TTL_S:
        return hit[1]
    try:
        flags = merge(await db.pool.fetch(LOAD, tenant_id))
    except Exception:
        log.exception("flag load failed for tenant %s, using last known values", tenant_id)
        return hit[1] if hit else {}
    _cache[tenant_id] = (now, flags)
    return flags


async def is_on(tenant_id: int, flag: str, key: str = "", default: bool = False) -> bool:
    return decide(await _load(tenant_id), tenant_id, flag, key, default)