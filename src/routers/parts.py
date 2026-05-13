"""
OSKAR — Part number intelligence endpoints (Sprint 3)

GET  /api/v1/parts/alias       Reverse alias lookup: customer P/N → SRX ITNO via MVXCDTA.MITPOP.
                               Returns full_match / partial_match / no_match states.
                               Replaces manual MOVEX search (~30 min → seconds). S3-1.

GET  /api/v1/parts/suggest-pn  Auto-generate the next available Scanfil APAC part number.
                               Format: LF + {2-char CUNO} + {2-digit commodity} + {4-digit seq}.
                               'LF' is the company prefix (not a lead-free marker). S3-2.

POST /api/v1/parts/autofill    Enrich an ecn_items row from DigiKey → Nexar → Movex.
                               Sets item_name (from supplier description, ≤30 chars) and
                               unit_of_measure (from MMS200MI.GetItmBasic). S3-3.
"""

from __future__ import annotations

from typing import Annotated, Literal

import httpx
import pybreaker
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.ai.base import sanitize_for_prompt
from src.adapters.ai.factory import get_ai_provider
from src.adapters.erp.movex import MovexRestAdapter
from src.adapters.suppliers.chain import SupplierChain
from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.services.ecn import ECNNotFound, ECNService
from src.services.ecn.commodity_codes import VALID_PROCUREMENT_GROUPS, VALID_PRODUCT_GROUPS, get_commodity_code

parts_router = APIRouter(prefix="/parts", tags=["parts"])


# ── Dependencies ─────────────────────────────────────────────────────────────

def _get_erp_adapter(request: Request) -> MovexRestAdapter:
    return request.app.state.erp_adapter


def _get_supplier_adapters(request: Request) -> list:
    return getattr(request.app.state, "supplier_adapters", [])


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


# ── S3-2: Part number suggestion ──────────────────────────────────────────────

class SuggestPNResponse(BaseModel):
    suggested_pn: str
    procurement_group: str
    product_group: str
    cuno: str
    commodity_code: str
    sequence: int


@parts_router.get(
    "/suggest-pn",
    response_model=SuggestPNResponse,
    summary="Suggest next available Scanfil APAC part number for a new item (S3-2)",
)
async def suggest_pn(
    procurement_group: Annotated[str, Query(min_length=2, max_length=5, description="Movex procurement group (MITMAS.MMPRGP)")],
    product_group: Annotated[str, Query(min_length=2, max_length=5, description="Movex product group (MITMAS.MMITCL)")],
    cuno: Annotated[str, Query(min_length=2, max_length=2, description="2-char Movex customer code (OCUSMA.OKCUNO)")],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    erp: Annotated[MovexRestAdapter, Depends(_get_erp_adapter)],
    commodity_override: Annotated[str | None, Query(max_length=2, description="Override when multiple commodity codes exist for this pair")] = None,
) -> SuggestPNResponse:
    """Suggest the next available part number for a new item.

    Resolves the commodity code from (procurement_group, product_group) using Engineering Team's
    ecn_item_upload_v13 matrix. When multiple codes exist for a pair (e.g. PAS/RES →
    11/12/13/14), commodity_override is required — returns 422 with commodity_options
    so the UI can prompt the engineer to choose.

    Queries MVXCDTA.MITMAS via GET /api/mitmas/next-sequence for the highest existing
    sequence under this prefix, then increments by one. Thread-safe as long as the
    engineer confirms the suggestion before creating the item in Movex.

    PN format: LF + {CUNO 2 chars} + {commodity 2 digits} + {seq 4 digits zero-padded}
    'LF' is the company prefix (Startronics/SRXGlobal legacy), not a lead-free marker.
    """
    prgp = procurement_group.upper().strip()
    itcl = product_group.upper().strip()
    cuno_upper = cuno.upper()

    # Validate groups exist in the commodity map
    if prgp not in VALID_PROCUREMENT_GROUPS or itcl not in VALID_PRODUCT_GROUPS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown (procurement_group, product_group) pair: ({prgp}, {itcl}). "
                   "Check Proc & Prod Group Matrix.",
        )

    code, valid_codes = get_commodity_code(prgp, itcl, commodity_override)

    # Pair exists but override not in valid list
    if code is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"No commodity code found for ({prgp}, {itcl}).",
        )

    # Override provided but not valid for this pair
    if commodity_override is not None:
        override_norm = commodity_override.upper().zfill(2)
        if override_norm not in valid_codes:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"commodity_options": valid_codes},
            )

    # Multiple codes and no override provided — prompt engineer to choose
    if len(valid_codes) > 1 and commodity_override is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"commodity_options": valid_codes},
        )

    prefix = f"LF{cuno_upper}{code}"

    try:
        seq = await erp.get_next_itno_sequence(prefix=prefix)
    except pybreaker.CircuitBreakerError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ERP system unavailable (circuit breaker open). Try again shortly.",
        )
    except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ERP connection failed after retries.",
        )

    suggested_pn = f"{prefix}{seq:04d}"

    return SuggestPNResponse(
        suggested_pn=suggested_pn,
        procurement_group=prgp,
        product_group=itcl,
        cuno=cuno_upper,
        commodity_code=code,
        sequence=seq,
    )


# ── S3-3: Stock code autofill ─────────────────────────────────────────────────

class AutofillRequest(BaseModel):
    ecn_id: str = Field(..., min_length=1)
    item_id: str = Field(..., min_length=1, description="OSKAR UUID — ecn_items.id")
    item_number: str = Field(
        ..., min_length=1, max_length=15,
        description="Movex stock code — MITMAS.MMITNO",
    )


class AutofillResponse(BaseModel):
    id: str
    ecn_id: str
    line_number: int
    is_new_item: bool
    item_number: str
    item_name: str | None
    description_2: str | None
    drawing_number: str | None
    drawing_created: bool
    procurement_group: str | None
    product_group: str | None
    unit_of_measure: str | None
    item_group: str | None
    customer_alias: str | None
    effectivity_type: str
    effectivity_from: str | None
    created_at: str
    updated_at: str
    mpns: list = []


def _item_to_response(item: object) -> AutofillResponse:
    return AutofillResponse(
        id=str(item.id),
        ecn_id=str(item.ecn_id),
        line_number=item.line_number,
        is_new_item=item.is_new_item,
        item_number=item.item_number,
        item_name=item.item_name,
        description_2=item.description_2,
        drawing_number=item.drawing_number,
        drawing_created=item.drawing_created,
        procurement_group=item.procurement_group,
        product_group=item.product_group,
        unit_of_measure=item.unit_of_measure,
        item_group=item.item_group,
        customer_alias=item.customer_alias,
        effectivity_type=item.effectivity_type,
        effectivity_from=item.effectivity_from,
        created_at=str(item.created_at),
        updated_at=str(item.updated_at),
        mpns=item.mpns,
    )


@parts_router.post(
    "/autofill",
    response_model=AutofillResponse,
    summary="Enrich ecn_items from supplier chain + Movex (S3-3)",
)
async def autofill_item(
    body: AutofillRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    erp: Annotated[MovexRestAdapter, Depends(_get_erp_adapter)],
    supplier_adapters: Annotated[list, Depends(_get_supplier_adapters)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AutofillResponse:
    """Enrich an ecn_items row with description and unit of measure.

    Lookup order:
      1. Supplier chain (DigiKey → Nexar → stubs) via the item's default MPN.
         Raw description passed through AIProvider.suggest_description() — smart
         summarisation when a real AI provider is configured, plain truncation via
         NoOpAIProvider when not (AI_PROVIDER_CLASS not set).
      2. MMS200MI.GetItmBasic via item_number → unit_of_measure (UNMS).
         Skipped for new items (is_new_item=True) — item not yet in Movex.

    Both steps are best-effort: a supplier miss or absent UNMS leaves that field
    unchanged. item_number is always confirmed regardless.
    """
    svc = ECNService(session)

    try:
        current_item = await svc.get_item(body.ecn_id, body.item_id)
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    updates: dict = {"item_number": body.item_number}

    # ── Supplier chain → item_name (via AI smart truncation) ─────────────────
    default_mpn = next((m.mpn for m in current_item.mpns if m.is_default), None)
    if default_mpn:
        chain = SupplierChain(session, supplier_adapters)
        supplier_data = await chain.get_part(default_mpn)
        raw_description = supplier_data.get("description", "")
        if raw_description:
            ai = get_ai_provider()
            safe = sanitize_for_prompt(raw_description)
            updates["item_name"] = ai.suggest_description(safe, max_len=30).content

    # ── Movex GetItmBasic → unit_of_measure ───────────────────────────────────
    if not current_item.is_new_item:
        try:
            movex_item = await erp.get_item(body.item_number)
        except pybreaker.CircuitBreakerError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ERP system unavailable (circuit breaker open). Try again shortly.",
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Item {body.item_number!r} not found in Movex.",
                )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"ERP returned unexpected status {exc.response.status_code}.",
            )
        except (httpx.ConnectError, httpx.TimeoutException):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="ERP connection failed after retries.",
            )

        unms = movex_item.get("UNMS", "").strip()
        if unms:
            updates["unit_of_measure"] = unms

    updated = await svc.update_item(body.ecn_id, body.item_id, **updates)
    return _item_to_response(updated)
