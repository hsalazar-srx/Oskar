# OSKAR — FastAPI Application Entry Point
# Uses skill: integration/rest-api-design v1.0
# Uses skill: architecture/audit-logging-framework v1.0

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.adapters.erp.movex import MovexRestAdapter
from src.adapters.suppliers.digikey import DigiKeyAdapter
from src.adapters.suppliers.nexar import NexarAdapter
from src.logging_config import configure_logging
from src.middleware.correlation import CorrelationIdMiddleware
from src.middleware.origin import OriginCheckMiddleware
from src.routers import v1_router
from src.routers.health import health_router

# Configure structlog before any other module emits a log record
configure_logging()


@asynccontextmanager
async def _lifespan(application: FastAPI):
    """Open shared connection pools for ERP and supplier adapters."""
    adapter = MovexRestAdapter()
    await adapter.open()
    application.state.erp_adapter = adapter

    supplier_adapters = []
    if os.getenv("DIGIKEY_CLIENT_ID"):
        digikey = DigiKeyAdapter()
        await digikey.open()
        supplier_adapters.append(digikey)
    if os.getenv("NEXAR_CLIENT_ID"):
        nexar = NexarAdapter()
        await nexar.open()
        supplier_adapters.append(nexar)
    application.state.supplier_adapters = supplier_adapters

    yield

    for sa in supplier_adapters:
        await sa.close()
    await adapter.close()


app = FastAPI(
    title="OSKAR Engineering Intelligence Platform",
    description="ECN workflow, BOM management, and Supplier Intelligence for Scanfil APAC",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=_lifespan,
)

# ── Middleware (order matters: correlation ID first, then origin check, then CORS) ───────────────
def _parse_origins(raw: str) -> list[str]:
    return [
        o.strip().rstrip("/").lower()
        for o in raw.split(",")
        if o.strip()
    ]


app.add_middleware(CorrelationIdMiddleware)
_cors_origins = _parse_origins(
    os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
)
app.add_middleware(OriginCheckMiddleware, allowed_origins=_cors_origins)
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
