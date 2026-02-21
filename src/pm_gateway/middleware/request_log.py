"""Request logging middleware.

Logs every HTTP request with method, path, status code, latency, and
a short request ID for correlation. The request_id is also injected into
request.state so router handlers can include it in ApiResponse.

Log format:
    INFO [POST] /api/v1/auth/login → 200 (23ms) req=a1b2c3d4
"""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("pm.request")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Inject short request ID into request state for use in handlers
        request.state.request_id = f"req_{uuid.uuid4().hex[:12]}"

        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "[%s] %s → %d (%.0fms) %s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request.state.request_id,
        )
        return response
