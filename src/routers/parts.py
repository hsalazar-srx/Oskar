"""
OSKAR — Part number intelligence endpoints (Sprint 3)

GET /api/v1/parts/alias   Reverse alias lookup: customer P/N → SRX ITNO via MVXCDTA.MITPOP.
                          Returns full_match / partial_match / no_match states.
                          Replaces manual MOVEX search (~30 min → seconds). S3-1.
"""

from __future__ import annotations

from typing import Annotated, Literal

import httpx
import pybreaker
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from src.adapters.erp.movex import MovexRestAdapter
from src.auth.dependencies import CurrentUser, get_current_user

parts_router = APIRouter(prefix="/parts", tags=["parts"])


# ── ERP adapter dependency ────────────────────────────────────────────────────

def _get_erp_adapter(request: Request) -> MovexRestAdapter:
    return request.app.state.erp_adapter


# ── Response models ───────────────────────────────────────────────────────────

class AliasCandidate(BaseModel):
    item_number: str
    alias_type: str | None
    alias_qualifier: str | None
    partner_code: str | None


class AliasLookupResponse(BaseModel):
    popn: str
    match_state: Literal["full_match", "partial_match", "no_match"]
    candidates: list[AliasCandidate] = []
    message: str


# ── Match state logic ─────────────────────────────────────────────────────────

_MESSAGES = {
    "full_match":    "Part number resolved to one SRX item. Review and confirm.",
    "partial_match": "Multiple SRX items share this alias. Select the correct one.",
    "no_match":      "No alias found in Movex. If this is a new part, set is_new_item=True.",
}


def _build_response(popn: str, records: list[dict]) -> AliasLookupResponse:
    count = len(records)
    if count == 0:
        state = "no_match"
    elif count == 1:
        state = "full_match"
    else:
        state = "partial_match"

    candidates = [
        AliasCandidate(
            item_number=r.get("ITNO", ""),
            alias_type=r.get("ALWT") or None,
            alias_qualifier=r.get("ALWQ") or None,
            partner_code=r.get("E0PA") or None,
        )
        for r in records
    ]

    return AliasLookupResponse(
        popn=popn,
        match_state=state,
        candidates=candidates,
        message=_MESSAGES[state],
    )


# ── Endpoint ──────────────────────────────────────────────────────────────────

@parts_router.get(
    "/alias",
    response_model=AliasLookupResponse,
    summary="Reverse alias lookup: customer P/N → SRX ITNO via MITPOP (S3-1)",
)
async def lookup_alias(
    popn: Annotated[str, Query(min_length=1, max_length=30, description="Customer part number (MITPOP.MPPOPN)")],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    erp: Annotated[MovexRestAdapter, Depends(_get_erp_adapter)],
    cuno: Annotated[str | None, Query(max_length=10, description="Customer/partner code (MITPOP.MPE0PA) — optional filter")] = None,
) -> AliasLookupResponse:
    """Look up which SRX internal item number(s) a customer part number maps to.

    Queries MVXCDTA.MITPOP via a custom DB2 endpoint on movex-rest-api.
    No M3 MI program supports this reverse direction (confirmed 2026-05-11).

    Three states:
    - full_match    — exactly one ITNO; engineer can auto-populate the item number field.
    - partial_match — multiple ITNOs; engineer must choose.
    - no_match      — POPN absent from MITPOP; engineer should set is_new_item=True.
    """
    try:
        records = await erp.lookup_by_alias(popn=popn.strip(), cuno=cuno)
    except pybreaker.CircuitBreakerError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ERP system unavailable (circuit breaker open). Try again shortly.",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ERP returned unexpected status {exc.response.status_code}.",
        )
    except (httpx.ConnectError, httpx.TimeoutException):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ERP connection failed after retries.",
        )

    return _build_response(popn.strip(), records)
