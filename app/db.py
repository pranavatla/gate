import json

import asyncpg

from app.config import DATABASE_URL

pool: asyncpg.Pool | None = None


async def _init(conn):
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def connect():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5, init=_init)


async def disconnect():
    if pool:
        await pool.close()