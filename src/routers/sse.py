"""
OSKAR SSE Endpoint — GET /api/v1/ecn/{ecn_id}/stream

Real-time ECN status push via PostgreSQL LISTEN/NOTIFY + Server-Sent Events.

Design notes:
- Uses asyncpg.connect() directly (NOT SQLAlchemy AsyncSession — incompatible with LISTEN).
  DSN built from env vars following the health.py pattern.
- Auth: JWT validated via Depends(get_current_user) before StreamingResponse is created.
  User is closed over in the async generator (not passed through StreamingResponse).
- Keepalive: yields {"ping": true} every ~25s to stay within IIS proxy idle timeout.
- Semaphore: caps concurrent SSE connections to 20 (safe on 2vCPU/4GB VM).
- pg_notify channel: ecn_<uuid> — one channel per ECN (not broadcast).
  Trigger wired in migration 0007 (trg_ecn_instances_notify).

ADR-007 upgrade path: this fulfils the SSE path documented in ADR-007 §Redis Elimination.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import AsyncGenerator

import asyncpg
import structlog
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse, StreamingResponse

from src.auth.dependencies import CurrentUser, get_current_user

log = structlog.get_logger(__name__)

sse_router = APIRouter(tags=["ecn-stream"])

# Safety valve — max concurrent SSE connections on this node.
# Keeps the 2vCPU/4GB VM from being exhausted by stale browser tabs.
_sse_semaphore = asyncio.Semaphore(20)

# SSE timeout before sending a keepalive ping (seconds).
# Must be less than IIS proxy idle timeout (typically 60–120s in production).
_NOTIFY_TIMEOUT = 25.0


def _build_dsn() -> str:
    return (
        f"postgresql://{os.getenv('OSKAR_DB_USER', 'oskar_app')}:"
        f"{os.getenv('OSKAR_DB_PASSWORD', '')}@"
        f"{os.getenv('OSKAR_DB_HOST', 'localhost')}:"
        f"{os.getenv('OSKAR_DB_PORT', '5432')}/"
        f"{os.getenv('OSKAR_DB_NAME', 'oskar')}"
    )


def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


async def _ecn_stream(
    ecn_id: str,
    user: CurrentUser,
) -> AsyncGenerator[str, None]:
    """Async generator — yields SSE-formatted strings.

    Lifecycle:
    1. Open raw asyncpg connection.
    2. Fetch current ECN row — yield error event and close if not found.
    3. Yield initial status event.
    4. LISTEN ecn_<ecn_id>.
    5. Loop: wait_for_notify with timeout.
       - Notification → yield ecn_status event.
       - TimeoutError  → yield keepalive ping.
       - CancelledError → break (client disconnected).
    6. finally: UNLISTEN, close connection.
    """
    conn: asyncpg.Connection | None = None
    channel = f"ecn_{ecn_id}"
    try:
        conn = await asyncpg.connect(_build_dsn())

        row = await conn.fetchrow(
            "SELECT status, ecn_number, updated_at "
            "FROM ecn_instances WHERE id = $1",
            ecn_id,
        )
        if row is None:
            yield _sse_event({"error": "ecn_not_found"})
            return

        yield _sse_event({
            "type": "ecn_status",
            "status": row["status"],
            "ecn_number": row["ecn_number"],
            "updated_at": str(row["updated_at"]),
        })

        await conn.execute(f"LISTEN {channel}")

        while True:
            try:
                notification = await conn.wait_for_notify(timeout=_NOTIFY_TIMEOUT)
                payload = json.loads(notification.payload)
                yield _sse_event({
                    "type": "ecn_status",
                    "status": payload.get("status"),
                    "ecn_number": payload.get("ecn_number"),
                    "updated_at": payload.get("updated_at"),
                })
            except asyncio.TimeoutError:
                yield _sse_event({"ping": True})
            except asyncio.CancelledError:
                break

    finally:
        if conn is not None:
            try:
                await conn.execute(f"UNLISTEN {channel}")
            except Exception:
                pass
            await conn.close()


@sse_router.get("/ecn/{ecn_id}/stream", response_model=None)
async def ecn_stream(
    ecn_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse | JSONResponse:
    """Stream ECN status changes via Server-Sent Events.

    Returns a streaming response of SSE events for the given ECN.
    Initial event contains the current status. Subsequent events fire when
    the ECN status changes (via pg_notify trigger trg_ecn_instances_notify).
    A keepalive ping is emitted every ~25s when there are no changes.

    Errors:
      401 — no valid JWT
      503 — server at SSE connection limit (20 concurrent)
    """
    if not _sse_semaphore._value:  # noqa: SLF001
        log.warning("sse_connection_limit_reached", ecn_id=ecn_id, username=user.username)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "sse_connection_limit_reached"},
        )

    async def _guarded_stream() -> AsyncGenerator[str, None]:
        async with _sse_semaphore:
            async for event in _ecn_stream(ecn_id, user):
                yield event

    return StreamingResponse(
        _guarded_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable Nginx/IIS buffering
        },
    )
