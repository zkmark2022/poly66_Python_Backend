"""Rate limiting middleware — TODO: not implemented in MVP.

Planned rules (from API contract §1.8):
  - Auth endpoints:  5 req/min/IP   (anti brute-force)
  - Order endpoint: 30 req/min/user (anti spam)
  - Query endpoints: 120 req/min/user

Implementation approach (when ready):
  1. Use Redis INCR + EXPIRE for fixed-window counting
  2. Key pattern: "ratelimit:{user_id_or_ip}:{endpoint_group}"
  3. Extract real client IP from X-Forwarded-For header (reverse proxy aware)
  4. Raise RateLimitError (9001) when limit exceeded
  5. Add Retry-After header to 429 responses

Example Redis logic:
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    if count > limit:
        raise RateLimitError()
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """TODO: Implement Redis-based rate limiting."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # TODO: check rate limit before proceeding
        return await call_next(request)
