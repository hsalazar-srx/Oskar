from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class NoCacheMiddleware(BaseHTTPMiddleware):
    """Set Cache-Control: no-store on all /api/ responses.

    Without this the browser's heuristic caching kicks in for GET requests
    that have no explicit Cache-Control header, causing stale API responses
    to be served from the disk cache until a hard refresh (Ctrl+Shift+R).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response
