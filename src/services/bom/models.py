"""OSKAR — src.services.bom service-layer data classes and error types.

No DB imports — pure Python types only, mirroring the src/services/ecn/models.py
convention (models.py holds dataclasses + error types; DB access lives elsewhere).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Slice A — single-level browse
# ---------------------------------------------------------------------------


@dataclass
class BOMLine:
    """One MPDMAT component line (B-1 record), normalised for the service layer.

    ref_des: None means "never recorded", which is deliberately distinct from
    [] ("recorded as having no designators"). get_single_level_bom always
    leaves it None — browse.py is pure and does not touch the DB; callers
    that want designators compose src.services.bom.ref_des.enrich_ref_des.

    customer_alias: still None everywhere — the forward item -> alias lookup
    (MMS025MI.GetAlias/LstAlias) has no ERPAdapter method yet.
    """

    sequence_number: int          # MSEQ
    component_number: str         # MTNO
    description: str              # ITDS
    operation_number: int         # OPNO
    quantity: float                # CNQT
    unit_of_measure: str            # PEUN
    from_date: int                  # FDAT (YYYYMMDD)
    to_date: int                    # TDAT (YYYYMMDD; 99999999 = open-ended)
    item_type: str | None = None      # ITTY
    status: str | None = None         # STAT
    ref_des: list[str] | None = None       # bom_circuit_refs (D4), via ref_des.enrich_ref_des
    customer_alias: str | None = None      # TODO: MMS025MI.GetAlias/LstAlias forward lookup — no adapter method yet


@dataclass
class BOMHead:
    """Single-level BOM head (MPDHED, B-1 'head' object) + its component lines."""

    item_number: str        # PRNO
    structure_type: str     # STRT
    facility: str           # FACI
    description: str        # ITDS
    lines: list[BOMLine] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Slice B — multi-level explosion + where-used
# ---------------------------------------------------------------------------


@dataclass
class BOMTreeNode:
    """One node in the assembled multi-level explosion tree (B-2, flat LEVL
    rows assembled client-side per the contract doc)."""

    component_number: str          # MTNO (PRNO for the synthetic root node)
    description: str               # ITDS
    operation_number: int           # OPNO
    quantity: float                  # CNQT — this node's own quantity under its immediate parent
    cumulative_quantity: float        # quantity extended through every ancestor's quantity
    item_type: str | None              # ITTY
    is_phantom: bool                    # ITTY == "9"
    children: list["BOMTreeNode"] = field(default_factory=list)


@dataclass
class WhereUsedLine:
    """One reverse-MPDMAT row (B-3): a parent assembly that consumes the
    queried component."""

    parent_item: str         # PRNO
    structure_type: str      # STRT
    facility: str            # FACI
    sequence_number: int     # MSEQ
    component_number: str    # MTNO — the component that was queried
    operation_number: int    # OPNO
    quantity: float            # CNQT
    unit_of_measure: str        # PEUN
    from_date: int               # FDAT
    to_date: int                  # TDAT


class BOMCycleError(Exception):
    """Raised by src.services.bom.explode's tree builder when the flat LEVL
    rows describe a component that is its own ancestor (or exceed max_depth,
    treated as the same failure mode — a well-formed BOM never needs to
    recurse past the depth cap)."""
