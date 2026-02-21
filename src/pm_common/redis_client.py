"""Redis client factory — used for rate limiting and sessions only.

NOT used for balance caching or freezing (those go through PostgreSQL).
Ref: Planning/Detail_Design/01_全局约定与数据库设计.md §3
"""

import redis.asyncio as aioredis

from config.settings import settings

_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Get or create the Redis connection pool."""
    global _redis_pool  # noqa: PLW0603
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
    return _redis_pool


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _redis_pool  # noqa: PLW0603
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None
