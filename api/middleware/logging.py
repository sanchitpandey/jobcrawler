"""
HTTP request logging middleware.

Logs every request with method, path, status code, and wall-clock duration.
Injects a short ``X-Request-ID`` header into each response so individual
requests can be correlated across log lines.

The request ID is stored in a ContextVar (``api.logger.request_id_var``)
for the lifetime of the request, so any logger called from a route handler
or dependency will automatically include it in structured JSON output.
"""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from api.logger import get_logger, request_id_var

log = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log each HTTP request at INFO level with timing and request-ID context."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())[:8]
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        status = 500

        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            level = log.warning if status >= 500 else (
                log.info if status < 400 else log.warning
            )
            level(
                "%s %s %d  %.1fms",
                request.method,
                request.url.path,
                status,
                duration_ms,
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": duration_ms,
                },
            )
            request_id_var.reset(token)

        response.headers["X-Request-ID"] = request_id
        return response
