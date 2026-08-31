"""OSKAR — src.services.bom.enrich — BOM supplier-attribute enrichment
(Slice F, I2-12).

For one BOM: resolve each component's default MPN from item_mpns, look that
MPN up through SupplierChain, and return the supplier attributes alongside
each component line. Also serves PLM's "Single Component Attribute Search"
parity, which is this with a one-line BOM.

── Why the lookup cap is the central design constraint ─────────────────────

A BOM has N component lines. Every distinct MPN is potentially one supplier
API call. The free tiers are small and hard-capped:

    element14  1,000 calls/day   (2/sec, tracked locally — no quota headers)
    DigiKey    1,000 calls/day
    Nexar        100 parts LIFETIME

A single 400-line BOM enriched naively spends 40% of a day's element14 budget
in one request, and a user who clicks the button twice spends most of the
rest. So:

  * CACHE FIRST. SupplierChain checks supplier_part_cache before any network
    call; with the split-TTL cache (migration 0033) descriptive attributes
    stay warm for 30 days, so a re-enrich of the same BOM is usually free.
  * LIVE LOOKUPS ARE CAPPED PER REQUEST. Past the cap, remaining components
    are returned marked `cap_reached` — visibly incomplete rather than
    silently missing, so the caller knows to re-run rather than concluding
    the data does not exist.
  * DEDUPLICATED. A BOM commonly uses one part at several sequence numbers;
    each repeat must not cost another call.

Note the cap counts DISTINCT MPNs actually looked up, not components — a
cache hit inside SupplierChain still counts, because this layer cannot see
whether the chain served from cache or network. That makes the cap a
conservative upper bound on API spend, which is the right direction to err.

── Status vocabulary ───────────────────────────────────────────────────────

Every component comes back with exactly one status, and the distinctions are
deliberate — collapsing any pair would hide something a user needs:

    enriched       supplier returned attributes
    no_mpn         no MPN on file for this component (an actionable finding
                   for purchasing, not an error)
    not_found      we knew what to ask; no supplier had it (a data finding)
    lookup_failed  we could not ask — outage, quota exhausted (an outage, NOT
                   the same as not_found)
    cap_reached    not attempted; this request's lookup budget was spent
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol, Sequence

import sqlalchemy as sa
import structlog

from src.services.bom.models import BOMHead

log = structlog.get_logger(__name__)

# Conservative by design: well under a single day's budget, so no one request
# can be the thing that exhausts it. Overridable per request (and by env for
# a deployment that has negotiated higher limits), but the default assumes
# the free tier.
DEFAULT_LIVE_LOOKUP_CAP = int(os.getenv("BOM_ENRICH_LOOKUP_CAP", "50"))

STATUS_ENRICHED = "enriched"
STATUS_NO_MPN = "no_mpn"
STATUS_NOT_FOUND = "not_found"
STATUS_LOOKUP_FAILED = "lookup_failed"
STATUS_CAP_REACHED = "cap_reached"


@dataclass
class EnrichedComponent:
    """One BOM component line plus whatever the supplier chain knew about it."""

    sequence_number: int
    component_number: str
    description: str
    mpn: str | None
    status: str
    attributes: dict[str, Any] = field(default_factory=dict)


class _SupplierChainLike(Protocol):
    async def get_part(self, mpn: str) -> dict[str, Any]: ...


async def _default_mpn_resolver(
    session: Any, item_numbers: Sequence[str]
) -> dict[str, str]:
    """component_number -> its current default MPN, from item_mpns.

    Only current defaults (is_default AND end_effective_date IS NULL) — the
    same predicate the partial unique index in migration 0025 enforces, so
    this can never return two MPNs for one item.

    One query for the whole BOM, not one per component.
    """
    if not item_numbers:
        return {}
    rows = await session.execute(
        sa.text(
            "SELECT item_number, mpn FROM item_mpns "
            "WHERE item_number = ANY(:items) "
            "  AND is_default AND end_effective_date IS NULL"
        ),
        {"items": list(item_numbers)},
    )
    return {r[0]: r[1] for r in rows.fetchall()}


async def enrich_bom_components(
    session: Any,
    head: BOMHead,
    chain: _SupplierChainLike,
    *,
    mpn_resolver: Callable[..., Awaitable[dict[str, str]]] | None = None,
    live_lookup_cap: int | None = None,
) -> list[EnrichedComponent]:
    """Enrich every component line on `head` with supplier attributes.

    Returns one EnrichedComponent per BOM line, always — components that
    could not be enriched are reported with a status explaining why, never
    dropped. A caller rendering this gets a complete BOM with gaps marked,
    which is what makes the gaps actionable.
    """
    cap = live_lookup_cap if live_lookup_cap is not None else DEFAULT_LIVE_LOOKUP_CAP
    resolver = mpn_resolver or _default_mpn_resolver

    component_numbers = [line.component_number for line in head.lines]
    if not component_numbers:
        return []

    mpn_by_component = await resolver(session, component_numbers)

    # MPN -> (attributes, status). Populated lazily so a repeated MPN costs
    # one lookup and one cap slot.
    looked_up: dict[str, tuple[dict[str, Any], str]] = {}
    lookups_spent = 0

    results: list[EnrichedComponent] = []
    for line in head.lines:
        mpn = mpn_by_component.get(line.component_number)

        if not mpn:
            # Costs no API call, so it must not consume a cap slot that a
            # real lookup could have used.
            results.append(
                EnrichedComponent(
                    sequence_number=line.sequence_number,
                    component_number=line.component_number,
                    description=line.description,
                    mpn=None,
                    status=STATUS_NO_MPN,
                )
            )
            continue

        if mpn not in looked_up:
            if lookups_spent >= cap:
                results.append(
                    EnrichedComponent(
                        sequence_number=line.sequence_number,
                        component_number=line.component_number,
                        description=line.description,
                        mpn=mpn,
                        status=STATUS_CAP_REACHED,
                    )
                )
                continue

            lookups_spent += 1
            try:
                data = await chain.get_part(mpn)
            except Exception as exc:  # noqa: BLE001 — one failure must not abort the BOM
                log.warning(
                    "bom.enrich.lookup_failed",
                    mpn=mpn,
                    component_number=line.component_number,
                    error=str(exc),
                )
                looked_up[mpn] = ({}, STATUS_LOOKUP_FAILED)
            else:
                looked_up[mpn] = (
                    (data, STATUS_ENRICHED) if data else ({}, STATUS_NOT_FOUND)
                )

        attributes, status = looked_up[mpn]
        results.append(
            EnrichedComponent(
                sequence_number=line.sequence_number,
                component_number=line.component_number,
                description=line.description,
                mpn=mpn,
                status=status,
                attributes=dict(attributes),
            )
        )

    log.info(
        "bom.enrich.completed",
        item_number=head.item_number,
        components=len(results),
        lookups_spent=lookups_spent,
        cap=cap,
    )
    return results
