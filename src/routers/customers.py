"""
OSKAR — Customer lookup endpoint

GET /api/v1/customers  List active Movex customers for the ECN header customer
                        dropdown. Queries OCUSMA via a custom DB2 endpoint on
                        movex-rest-api (no M3 MI program lists customers).
"""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from src.adapters.erp.movex import MovexRestAdapter
from src.auth.dependencies import CurrentUser, get_current_user

customers_router = APIRouter(prefix="/customers", tags=["customers"])


def _get_erp_adapter(request: Request) -> MovexRestAdapter:
    return request.app.state.erp_adapter


class CustomerEntry(BaseModel):
    cuno: str
    name: str | None


@customers_router.get(
    "",
    response_model=list[CustomerEntry],
    summary="List active Movex customers for the ECN customer dropdown",
)
async def list_customers(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    erp: Annotated[MovexRestAdapter, Depends(_get_erp_adapter)],
) -> list[CustomerEntry]:
    """List active Movex customers (OCUSMA, status=active) via movex-rest-api.

    Does not include the 'AC' generic-stock pseudo-customer — that option is added
    client-side, since it is not a real OCUSMA row (see
    ai/memory/02-movex-erp-authority.md §10).
    """
    try:
        records = await erp.list_customers()
    except RuntimeError as exc:
        if "circuit breaker" not in str(exc):
            raise
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

    return [
        CustomerEntry(cuno=r.get("cuno", ""), name=r.get("name") or None)
        for r in records
    ]
