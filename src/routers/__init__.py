"""
OSKAR API Router — /api/v1/ prefix (Non-Negotiable #13, PRE-4)

ALL FastAPI routes must be registered on v1_router.
Never register routes directly on the FastAPI app instance.

Usage in main.py:
    from src.routers import v1_router
    app.include_router(v1_router)

Usage in module routers:
    from src.routers import v1_router

    @v1_router.get("/ecn/")
    async def list_ecns(): ...

This produces: GET /api/v1/ecn/
"""

from fastapi import APIRouter

from src.routers.admin import admin_router
from src.routers.auth import auth_router
from src.routers.ecn import ecn_router
from src.routers.sse import sse_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(auth_router)
v1_router.include_router(ecn_router)
v1_router.include_router(sse_router)
v1_router.include_router(admin_router)
