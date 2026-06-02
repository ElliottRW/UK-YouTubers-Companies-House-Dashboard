import json
import time
import aiosqlite
from pathlib import Path
from typing import Any, Callable, Optional

DB_PATH = Path(__file__).parent.parent / "data" / "cache.db"


async def init_cache():
    DB_PATH.parent.mkdir(exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expires_at REAL NOT NULL
            )
        """)
        await db.commit()


async def cache_get(key: str) -> Optional[Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
    if row is None:
        return None
    value, expires_at = row
    if 0 < expires_at < time.time():
        await cache_delete(key)
        return None
    return json.loads(value)


async def cache_set(key: str, value: Any, ttl: float = 0):
    # ttl=0 means permanent
    expires_at = (time.time() + ttl) if ttl > 0 else 0
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
            (key, json.dumps(value, default=str), expires_at),
        )
        await db.commit()


async def cache_delete(key: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM cache WHERE key = ?", (key,))
        await db.commit()


async def cache_delete_prefix(prefix: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM cache WHERE key LIKE ?", (f"{prefix}%",))
        await db.commit()


async def get_or_fetch(key: str, fetch_fn: Callable, ttl: float = 0) -> Any:
    cached = await cache_get(key)
    if cached is not None:
        return cached
    result = await fetch_fn()
    if result is not None:
        await cache_set(key, result, ttl)
    return result
