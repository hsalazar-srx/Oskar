"""
OSKAR — Admin endpoints

POST /api/v1/admin/ecn-digest  — On-demand ECN digest trigger (G-5)

Requires DC role (OSKAR-DC group).  Returns 202 Accepted immediately;
the Celery task runs asynchronously.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.tasks.ecn_notifications import send_ecn_digest

admin_router = APIRouter(prefix="/admin", tags=["admin"])

_DC_GROUP = "OSKAR-DC"


@admin_router.post(
    "/ecn-digest",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_ecn_digest(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Trigger the ECN digest email on demand.

    Queues the Celery task and returns immediately.
    Restricted to DC role (OSKAR-DC group).
    """
    if _DC_GROUP not in user.groups:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Document Controllers may trigger the ECN digest.",
        )
    send_ecn_digest.delay()
    return {"status": "queued"}
