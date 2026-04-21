# OSKAR — Health Endpoints (P0-4)
# Implements: ai/memory/11-observability.md §6
#
# GET /api/v1/health/live   — liveness: process is running (Docker HEALTHCHECK)
# GET /api/v1/health/ready  — readiness: PG + Redis + LDAP reachable (IIS routing guard)
#
# Registered in src/routers/__init__.py on v1_router.

import os
import time

import structlog
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

log = structlog.get_logger(__name__)

health_router = APIRouter(prefix="/health", tags=["system"])


@health_router.get("/live")
async def liveness() -> dict:
    """Liveness probe — confirms the process is running.

    Used by Docker HEALTHCHECK. Returns 200 as long as the process is alive.
    Does NOT check external dependencies (that is readiness).
    """
    return {"status": "live", "service": "oskar-app"}


@health_router.get("/ready")
async def readiness() -> JSONResponse:
    """Readiness probe — confirms all dependencies are reachable.

    Checks: PostgreSQL, Redis, LDAP.
    Returns 200 {"status": "ready"} when all pass.
    Returns 503 {"status": "degraded"} with failing check identified.

    Used by IIS reverse proxy to gate traffic before routing.
    """
    checks: dict[str, str] = {}
    failed = False

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    try:
        import asyncpg

        db_url = (
            f"postgresql://{os.getenv('OSKAR_DB_USER', 'oskar_app')}:"
            f"{os.getenv('OSKAR_DB_PASSWORD', '')}@"
            f"{os.getenv('OSKAR_DB_HOST', 'localhost')}:"
            f"{os.getenv('OSKAR_DB_PORT', '5432')}/"
            f"{os.getenv('OSKAR_DB_NAME', 'oskar')}"
        )
        conn = await asyncpg.connect(db_url, timeout=3)
        await conn.execute("SELECT 1")
        await conn.close()
        checks["postgres"] = "ok"
    except Exception as exc:
        log.warning("health_check_postgres_failed", error=str(exc))
        checks["postgres"] = f"error: {type(exc).__name__}"
        failed = True

    # ── Redis ─────────────────────────────────────────────────────────────────
    try:
        import redis.asyncio as aioredis

        r = aioredis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD") or None,
            socket_connect_timeout=3,
        )
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as exc:
        log.warning("health_check_redis_failed", error=str(exc))
        checks["redis"] = f"error: {type(exc).__name__}"
        failed = True

    # ── LDAP ──────────────────────────────────────────────────────────────────
    try:
        import ssl

        from ldap3 import AUTO_BIND_NO_TLS, Connection, Server, Tls

        tls = Tls(validate=ssl.CERT_REQUIRED)
        server = Server(
            os.getenv("LDAP_SERVER", "ldaps://srxglobal.local"),
            port=int(os.getenv("LDAP_PORT", "636")),
            use_ssl=True,
            tls=tls,
            connect_timeout=3,
        )
        conn = Connection(
            server,
            user=os.getenv("LDAP_BIND_DN", ""),
            password=os.getenv("LDAP_BIND_PW", ""),
            auto_bind=AUTO_BIND_NO_TLS,
            raise_exceptions=True,
        )
        conn.unbind()
        checks["ldap"] = "ok"
    except Exception as exc:
        log.warning("health_check_ldap_failed", error=str(exc))
        checks["ldap"] = f"error: {type(exc).__name__}"
        failed = True

    if failed:
        log.error("readiness_check_degraded", checks=checks)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "degraded", "checks": checks},
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "ready", "checks": checks},
    )
