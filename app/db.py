import asyncpg

from app.config import DATABASE_URL

pool: asyncpg.Pool | None = None


async def connect():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)


async def disconnect():
    if pool:
        await pool.close()
