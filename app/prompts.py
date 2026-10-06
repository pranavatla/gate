"""Prompt registry resolver.

A tenant refers to a prompt by name. The gateway looks up the rollout for
(tenant, name) and picks the stable or the candidate version. The pick is
deterministic: the same sticky key always lands in the same bucket (0-99),
so one user keeps seeing the same variant while a rollout is running.
"""
import hashlib
import time
from dataclasses import dataclass

from fastapi import HTTPException

from app import db

CACHE_TTL_S = 15  # a rollout change can take up to this long to be seen
_cache: dict[tuple[int, str], tuple[float, "Rollout"]] = {}


@dataclass(frozen=True, slots=True)
class Rollout:
    stable_version: int
    stable_body: str
    candidate_version: int | None
    candidate_body: str | None
    candidate_pct: int


@dataclass(frozen=True, slots=True)
class ResolvedPrompt:
    name: str
    version: int
    body: str
    variant: str  # "stable" or "candidate"


def bucket(tenant_id: int, name: str, key: str) -> int:
    """Map (tenant, prompt, sticky key) to a stable number from 0 to 99."""
    digest = hashlib.sha256(f"{tenant_id}:{name}:{key}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % 100


def pick(rollout: Rollout, tenant_id: int, name: str, key: str) -> ResolvedPrompt:
    """Pure decision logic, no database. Easy to unit test."""
    if (
        rollout.candidate_version is not None
        and rollout.candidate_body is not None
        and bucket(tenant_id, name, key) < rollout.candidate_pct
    ):
        return ResolvedPrompt(name, rollout.candidate_version, rollout.candidate_body, "candidate")
    return ResolvedPrompt(name, rollout.stable_version, rollout.stable_body, "stable")


LOAD = """
SELECT r.stable_version, s.body AS stable_body,
       r.candidate_version, c.body AS candidate_body, r.candidate_pct
FROM prompt_rollouts r
JOIN prompt_versions s
  ON s.tenant_id = r.tenant_id AND s.name = r.name AND s.version = r.stable_version
LEFT JOIN prompt_versions c
  ON c.tenant_id = r.tenant_id AND c.name = r.name AND c.version = r.candidate_version
WHERE r.tenant_id = $1 AND r.name = $2
"""


async def load_rollout(tenant_id: int, name: str) -> Rollout:
    now = time.monotonic()
    hit = _cache.get((tenant_id, name))
    if hit and now - hit[0] < CACHE_TTL_S:
        return hit[1]

    row = await db.pool.fetchrow(LOAD, tenant_id, name)
    if row is None:
        raise HTTPException(400, f"Unknown prompt '{name}' for this tenant")

    rollout = Rollout(**dict(row))
    _cache[(tenant_id, name)] = (now, rollout)
    return rollout


async def resolve(tenant_id: int, name: str, key: str) -> ResolvedPrompt:
    return pick(await load_rollout(tenant_id, name), tenant_id, name, key)
