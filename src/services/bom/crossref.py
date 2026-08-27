"""OSKAR — src.services.bom.crossref — ECN BOM-change cross-reference advisory
(Slice F, I2-12).

Answers, for one ECN: "this change removes or supersedes component X from
assembly P — what OTHER live assemblies still consume X?"

Removing a component from one BOM is routine. Not noticing it is shared with
five other live assemblies is how a routine change becomes a production
incident. This surfaces that at review time.

ADVISORY ONLY — it never blocks a transition. Deliberate: the reader is a
human at review time, so a false positive costs a glance while a false
negative costs a production surprise. The bias is toward reporting.

The same reasoning drives the ERP-failure behaviour. If Movex is unreachable
the finding is returned with check_failed=True rather than omitted — an empty
result must never be ambiguous between "checked, all clear" and "could not
check". Silently returning [] on an outage would read as all-clear on the
review screen, which is the one failure mode that actually matters here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Protocol, Sequence

import structlog

from src.services.bom.explode import assemble_where_used

log = structlog.get_logger(__name__)

# Only these change types can orphan or supersede a component elsewhere.
# ADD cannot — adding a component to a BOM takes nothing away from any other
# assembly, so checking it would burn an ERP round trip per row for a finding
# that can never fire.
_CHECKED_CHANGE_TYPES = frozenset({"DELETE", "CHANGE"})

_OPEN_ENDED_TDAT = 99999999


class _BOMChangeLike(Protocol):
    """Structural view of the BOMChangeResponse fields this module reads.

    Deliberately narrow: keeping this to four attributes is what lets the
    tests build tiny stand-ins instead of full 20-field dataclasses, and
    documents exactly what the advisory depends on.
    """

    id: str
    change_type: str
    component_number: str
    parent_item_number: str


@dataclass
class CrossRefFinding:
    """One component that this ECN removes/supersedes and that other live
    assemblies still consume.

    other_parents excludes the change's own parent — the ECN is already
    changing that one, so echoing it back would be noise on every row.

    parents_also_on_this_ecn is the subset of other_parents that this SAME ECN
    also touches. Those are a weaker signal (someone is already looking at
    them) and the UI can de-emphasise them, but they are still reported —
    "handled on this ECN" is a judgment for the reviewer, not for this code.
    """

    bom_change_id: str
    component_number: str
    parent_item_number: str
    change_type: str
    other_parents: list[str] = field(default_factory=list)
    parents_also_on_this_ecn: list[str] = field(default_factory=list)
    check_failed: bool = False


def _today_yyyymmdd() -> int:
    return int(datetime.now(timezone.utc).strftime("%Y%m%d"))


def _is_live(to_date: int, today: int) -> bool:
    """to_date is INCLUSIVE — a line valid through today is still a consumer.

    Expired lines are excluded because warning about them would be a false
    positive on every long-lived component that has ever been superseded.
    """
    return to_date >= today


async def build_bom_crossref(
    erp: Any,
    bom_changes: Sequence[_BOMChangeLike],
    *,
    facility: str,
    today: int | None = None,
) -> list[CrossRefFinding]:
    """Build the advisory for one ECN's BOM changes.

    One ERP where-used call per DISTINCT component, not per row — an ECN can
    carry hundreds of BOM change rows and many will share components.
    """
    checked = [c for c in bom_changes if c.change_type in _CHECKED_CHANGE_TYPES]
    if not checked:
        return []

    as_of = today if today is not None else _today_yyyymmdd()

    # Every parent this ECN touches — used to mark findings whose other-parent
    # is already in scope on this same ECN.
    parents_on_ecn = {c.parent_item_number for c in bom_changes}

    # Cache per distinct component. Value is (parents, failed).
    cache: dict[str, tuple[list[str], bool]] = {}

    findings: list[CrossRefFinding] = []
    for change in checked:
        component = change.component_number
        if component not in cache:
            cache[component] = await _live_parents(erp, component, facility, as_of)
        parents, failed = cache[component]

        if failed:
            findings.append(
                CrossRefFinding(
                    bom_change_id=change.id,
                    component_number=component,
                    parent_item_number=change.parent_item_number,
                    change_type=change.change_type,
                    check_failed=True,
                )
            )
            continue

        others = sorted(p for p in parents if p != change.parent_item_number)
        if not others:
            continue

        findings.append(
            CrossRefFinding(
                bom_change_id=change.id,
                component_number=component,
                parent_item_number=change.parent_item_number,
                change_type=change.change_type,
                other_parents=others,
                parents_also_on_this_ecn=[p for p in others if p in parents_on_ecn],
            )
        )

    return findings


async def _live_parents(
    erp: Any, component: str, facility: str, as_of: int
) -> tuple[list[str], bool]:
    """Distinct live parent assemblies consuming `component`.

    Returns (parents, check_failed). A failure on one component must not lose
    the findings for every other component on the ECN, so the exception is
    caught here per-component rather than allowed to abort the whole advisory.
    """
    try:
        payload = await erp.get_where_used(component, facility)
    except Exception as exc:  # noqa: BLE001 — advisory must degrade, not raise
        log.warning(
            "bom.crossref.where_used_failed",
            component_number=component,
            facility=facility,
            error=str(exc),
        )
        return [], True

    lines = assemble_where_used(payload)
    parents = {ln.parent_item for ln in lines if _is_live(ln.to_date, as_of)}
    return sorted(parents), False
