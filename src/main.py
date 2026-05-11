# OSKAR — FastAPI Application Entry Point
# Uses skill: integration/rest-api-design v1.0
# Uses skill: architecture/audit-logging-framework v1.0

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.adapters.erp.movex import MovexRestAdapter
from src.logging_config import configure_logging
from src.middleware.correlation import CorrelationIdMiddleware
from src.routers import v1_router
from src.routers.health import health_router

# Configure structlog before any other module emits a log record
configure_logging()


@asynccontextmanager
async def _lifespan(application: FastAPI):
    """Open/close the shared MovexRestAdapter connection pool."""
    adapter = MovexRestAdapter()
    await adapter.open()
    application.state.erp_adapter = adapter
    yield
    await adapter.close()


app = FastAPI(
    title="OSKAR Engineering Intelligence Platform",
    description="ECN workflow, BOM management, and Supplier Intelligence for Scanfil APAC",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=_lifespan,
)

# ── Middleware (order matters: correlation ID first, then CORS) ───────────────
app.add_middleware(CorrelationIdMiddleware)
_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(v1_router)
v1_router.include_router(health_router)


@app.get("/health", tags=["system"])
async def health() -> dict:
    """Unversioned health check — used by Docker HEALTHCHECK and IIS reverse proxy.

    For full liveness/readiness checks use:
      GET /api/v1/health/live
      GET /api/v1/health/ready
    """
    return {"status": "ok", "service": "oskar-app"}
