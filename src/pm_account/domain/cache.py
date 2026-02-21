"""Account balance cache — TODO: implement in Phase 2.

Phase 2 cache to add:
  - Hot account balance caching with 5s TTL
  - Cache key: f"account:balance:{user_id}"
  - Write-through: DB first, then cache invalidate
  - Read: cache-aside (check cache → DB on miss → populate cache)

MVP note: All balance reads go directly to PostgreSQL.
"""
