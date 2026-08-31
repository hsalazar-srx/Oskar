"""OSKAR — src.services.bom.mpn_prefill — MPN-not-found → "Create ECN"
prefill (Slice F, I2-12).

The dead end this closes: an engineer searches for an MPN, Oskar's master
does not have it, and today that is where the trail stops. They must leave
the search, start an ECN by hand, remember to tick the right scope box, and
retype the MPN they just searched for. Each of those is a chance to get it
wrong — particularly the scope flag, which silently determines whether the
Supply Chain reviewer is ever asked to look (migration 0021's step
conditions route on add_mpn).

This builds a ready-to-submit ECN draft with the flag already set and the MPN
staged.

── A prefill, deliberately not a create ────────────────────────────────────

This function returns a PAYLOAD. The caller posts it to the existing ECN
create endpoint. ECN creation carries workflow rules, numbering and
audit-chain concerns, and a convenience path that created ECNs its own way
would drift from the real one the first time either changed. One creation
route, several ways to fill in the form.

── Supplier lookup is best-effort ──────────────────────────────────────────

The supplier chain is consulted to pre-fill the description and attributes,
but a failure never blocks: a prefill that errored because DigiKey was down
would be worse than one with an empty description. `supplier_data_found`
tells the caller which happened, so the UI can say "we could not reach the
suppliers" rather than implying the part does not exist anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog

log = structlog.get_logger(__name__)

# ecn_instances.title is VARCHAR(200). A payload that fails on insert because
# of a long MPN would be a worse dead end than the one this replaces.
_MAX_TITLE_LEN = 200

# Staged-row fields worth carrying over from a supplier hit, mapped from the
# supplier chain's vocabulary to ecn_mpns column names. Only fields that
# ecn_mpns actually has — anything else would be silently dropped on insert.
_SUPPLIER_TO_ECN_MPN = {
    "manufacturer": "manufacturer",
    "lifecycle": "lifecycle",
    "lead_time_weeks": "lead_time_weeks",
    "packaging_type": "packaging_type",
    "msl_level": "msl_level",
}


class _SupplierChainLike(Protocol):
    async def get_part(self, mpn: str) -> dict[str, Any]: ...


@dataclass
class MPNPrefill:
    """A ready-to-post ECN draft plus the MPN row to stage onto it."""

    ecn_draft: dict[str, Any]
    staged_mpn: dict[str, Any]
    supplier_data_found: bool = False
    supplier_attributes: dict[str, Any] = field(default_factory=dict)


async def build_mpn_ecn_prefill(
    mpn: str,
    chain: _SupplierChainLike,
    *,
    facility: str,
) -> MPNPrefill:
    """Build an ECN draft payload for adding `mpn`.

    Raises ValueError on an empty MPN — there is nothing to prefill, and
    returning a half-built draft would put the user in a worse position than
    an honest error.
    """
    cleaned = mpn.strip().upper()
    if not cleaned:
        raise ValueError("MPN is required to build a prefill.")

    supplier_data: dict[str, Any] = {}
    found = False
    try:
        supplier_data = await chain.get_part(cleaned) or {}
        found = bool(supplier_data)
    except Exception as exc:  # noqa: BLE001 — best-effort, must never block
        log.warning("mpn.prefill.supplier_lookup_failed", mpn=cleaned, error=str(exc))

    description = str(supplier_data.get("description", "")).strip()
    manufacturer = str(supplier_data.get("manufacturer", "")).strip()

    title = f"Add MPN {cleaned}"
    if len(title) > _MAX_TITLE_LEN:
        title = title[:_MAX_TITLE_LEN]

    body_lines = [f"Add manufacturer part number {cleaned} to the item master."]
    if manufacturer:
        body_lines.append(f"Manufacturer: {manufacturer}")
    if description:
        body_lines.append(f"Supplier description: {description}")
    if not found:
        body_lines.append(
            "No supplier data was available for this MPN at the time of drafting."
        )

    ecn_draft: dict[str, Any] = {
        "title": title,
        "description": "\n".join(body_lines),
        "facility": facility,
        # The only scope this ECN actually has. Over-scoping drags in
        # reviewers with nothing to review.
        "add_mpn": True,
    }

    staged_mpn: dict[str, Any] = {"mpn": cleaned, "is_default": True}
    for supplier_key, column in _SUPPLIER_TO_ECN_MPN.items():
        value = supplier_data.get(supplier_key)
        # Omit rather than blank: a staged row full of empty strings would
        # overwrite real values if merged against an existing item later.
        if value not in (None, ""):
            staged_mpn[column] = value

    return MPNPrefill(
        ecn_draft=ecn_draft,
        staged_mpn=staged_mpn,
        supplier_data_found=found,
        supplier_attributes=dict(supplier_data),
    )
