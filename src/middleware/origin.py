"""Origin header enforcement for state-mutating requests (ADR-006)."""
from __future__ import annotations

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

log = structlog.get_logger(__name__)

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _normalise_origin(origin: str) -> str:
    return origin.strip().rstrip("/").lower()


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """Reject cross-site state mutations when Origin is not in the allowlist."""

    def __init__(self, app, allowed_origins: list[str]) -> None:
        super().__init__(app)
        self._allowed = {_normalise_origin(o) for o in allowed_origins}

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in _MUTATING_METHODS:
            origin = request.headers.get("Origin")
            if origin:
                origin = _normalise_origin(origin)
                if origin not in self._allowed:
                    log.warning(
                        "csrf_origin_rejected",
                        origin=origin,
                        method=request.method,
                        path=request.url.path,
                    )
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Origin not allowed"},
                    )
        return await call_next(request)
