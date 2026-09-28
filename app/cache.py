import hashlib
import json
import logging
from dataclasses import dataclass

from app import db
from app.embeddings import embed
from app.schemas import ChatRequest, ChatResponse

log = logging.getLogger("gate.cache")

LOOKUP_SQL = """
SELECT id, response, 1 - (embedding <=> $1::vector) AS similarity
FROM semantic_cache
WHERE tenant_id = $2 AND scope = $3 AND expires_at > now()
ORDER BY embedding <=> $1::vector
LIMIT 1
"""

INSERT_SQL = """
INSERT INTO semantic_cache (tenant_id, scope, question, embedding, response, expires_at)
VALUES ($1, $2, $3, $4::vector, $5, now() + make_interval(secs => $6))
"""


@dataclass
class CacheLookup:
    status: str
    response: ChatResponse | None = None
    similarity: float | None = None
    vector: str | None = None
    embed_tokens: int = 0


def _settings(tenant) -> dict:
    return (tenant.policy or {}).get("cache") or {}


def _scope(tenant, req: ChatRequest) -> str:
    raw = json.dumps([tenant.id, req.model, req.system or "", req.max_tokens])
    return hashlib.sha256(raw.encode()).hexdigest()


def _to_pgvector(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


async def lookup(tenant, req: ChatRequest) -> CacheLookup:
    cfg = _settings(tenant)
    if not cfg.get("enabled"):
        return CacheLookup("off")
    if len(req.messages) != 1:
        return CacheLookup("skip")

    try:
        values, tokens = await embed(req.messages[0].content)
        vector = _to_pgvector(values)
        row = await db.pool.fetchrow(LOOKUP_SQL, vector, tenant.id, _scope(tenant, req))
    except Exception as e:
        log.warning("cache lookup failed, continuing without cache: %s", e)
        return CacheLookup("error")

    similarity = float(row["similarity"]) if row else None

    if row and similarity >= cfg.get("threshold", 0.95):
        await db.pool.execute("UPDATE semantic_cache SET hits = hits + 1 WHERE id = $1", row["id"])
        return CacheLookup("hit", ChatResponse(**row["response"]), similarity, vector, tokens)

    return CacheLookup("miss", None, similarity, vector, tokens)


async def store(tenant, req: ChatRequest, found: CacheLookup, resp: ChatResponse):
    if found.status != "miss":
        return
    ttl = float(_settings(tenant).get("ttl_s", 86400))
    try:
        await db.pool.execute(
            INSERT_SQL, tenant.id, _scope(tenant, req), req.messages[0].content,
            found.vector, resp.model_dump(), ttl,
        )
    except Exception as e:
        log.warning("cache store failed: %s", e)
