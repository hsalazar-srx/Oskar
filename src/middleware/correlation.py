# OSKAR — Correlation ID Middleware (P0-4)
# Implements: ai/memory/11-observability.md §4
#
# Generates a UUID4 correlation_id at every request boundary.
# If X-Correlation-ID header is present (e.g. from IIS reverse proxy), uses it.
# Stores in ContextVar so all log records in the request share the same ID.
# Passes to Celery tasks via apply_async(kwargs={"correlation_id": ...}).
# Returns X-Correlation-ID in every response header.

import uuid
from contextvars import ContextVar

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Module-level ContextVar — structlog reads this via merge_contextvars
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

log = structlog.get_logger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to every request/response cycle.

    Usage in src/main.py:
        from src.middleware.correlation import CorrelationIdMiddleware
        app.add_middleware(CorrelationIdMiddleware)

    Usage in any module:
        from src.middleware.correlation import correlation_id_var
        cid = correlation_id_var.get()

    Usage when dispatching Celery tasks:
        task.apply_async(kwargs={"correlation_id": correlation_id_var.get()})
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Honour inbound header from IIS or upstream proxy
        inbound = request.headers.get("X-Correlation-ID", "").strip()
        correlation_id = inbound if inbound else str(uuid.uuid4())

        # Bind to ContextVar — structlog.contextvars.merge_contextvars picks this up
        token = correlation_id_var.set(correlation_id)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        try:
            response: Response = await call_next(request)
        finally:
            correlation_id_var.reset(token)
            structlog.contextvars.clear_contextvars()

        response.headers["X-Correlation-ID"] = correlation_id
        return response


def get_correlation_id() -> str:
    """Return the current request's correlation ID, or empty string outside a request."""
    return correlation_id_var.get()
