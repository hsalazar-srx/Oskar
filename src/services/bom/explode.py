"""OSKAR — src.services.bom.explode — multi-level explosion tree + where-used
(Slice B, ADR-012).

build_bom_tree assembles B-2's flat, depth-first LEVL rows into a BOMTreeNode
tree client-side (Oskar's job per the contract doc — the movex-rest-api
recursive CTE returns the flat Stargile shape, not a nested one). Pure
function: dict/list in, BOMTreeNode out, no I/O.

Cycle guard: a well-formed BOM never needs to recurse past max_depth, and a
component can never legitimately be its own ancestor — both conditions raise
BOMCycleError rather than recursing forever. This defends the tree builder
against malformed/corrupted upstream data (the movex-rest-api CTE is itself
depth-capped and meant to be cycle-guarded server-side per the contract doc,
but Oskar's assembly step does not trust that blindly).

assemble_where_used maps B-3's flat records into WhereUsedLine dataclasses.
"""

from __future__ import annotations

from typing import Any

from src.services.bom.models import BOMCycleError, BOMTreeNode, WhereUsedLine

_OPEN_ENDED_TDAT = 99999999


def _index_children_by_parent(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        parent = str(record["PRNO"]).strip()
        children_by_parent.setdefault(parent, []).append(record)
    return children_by_parent


def build_bom_tree(
    item_number: str,
    records: list[dict[str, Any]],
    *,
    max_depth: int = 12,
) -> BOMTreeNode:
    """Assemble a BOMTreeNode tree rooted at item_number from B-2's flat
    depth-first records list.

    The root node itself carries quantity=1.0 / cumulative_quantity=1.0 (one
    of itself); every other node's cumulative_quantity is its own quantity
    extended through every ancestor's quantity (parent.cumulative_quantity *
    own quantity).

    Raises BOMCycleError when a component is its own ancestor, or when
    max_depth is exceeded while descending (treated as the same failure mode
    — see module docstring).
    """
    children_by_parent = _index_children_by_parent(records)

    def _build(
        component_number: str,
        description: str,
        operation_number: int,
        quantity: float,
        cumulative_quantity: float,
        item_type: str | None,
        depth: int,
        ancestors: frozenset[str],
    ) -> BOMTreeNode:
        if depth > max_depth:
            raise BOMCycleError(
                f"max_depth={max_depth} exceeded while descending into {component_number!r} "
                "— probable cycle in the source data"
            )
        if component_number in ancestors:
            raise BOMCycleError(
                f"cycle detected: {component_number!r} is its own ancestor"
            )

        children = [
            _build(
                str(rec["MTNO"]).strip(),
                str(rec.get("ITDS", "")).strip(),
                int(rec["OPNO"]),
                float(rec["CNQT"]),
                cumulative_quantity * float(rec["CNQT"]),
                rec.get("ITTY"),
                depth + 1,
                ancestors | {component_number},
            )
            for rec in children_by_parent.get(component_number, [])
        ]

        return BOMTreeNode(
            component_number=component_number,
            description=description,
            operation_number=operation_number,
            quantity=quantity,
            cumulative_quantity=cumulative_quantity,
            item_type=item_type,
            is_phantom=(item_type == "9"),
            children=children,
        )

    return _build(item_number, "", 0, 1.0, 1.0, None, 0, frozenset())


def rollup_quantities(root: BOMTreeNode) -> dict[str, float]:
    """Total cumulative_quantity per component_number across every tree
    position, excluding the root itself (the root is the assembly being
    built, not a component of itself).

    A component repeated at multiple tree positions (e.g. a resistor used
    both directly and inside a subassembly) has its cumulative_quantity from
    each position summed here — "how much of this component do I need in
    total to build one root assembly."
    """
    totals: dict[str, float] = {}

    def _walk(node: BOMTreeNode, is_root: bool) -> None:
        if not is_root:
            totals[node.component_number] = totals.get(node.component_number, 0.0) + node.cumulative_quantity
        for child in node.children:
            _walk(child, False)

    _walk(root, True)
    return totals


def assemble_where_used(payload: dict[str, Any]) -> list[WhereUsedLine]:
    """Map B-3's raw response into WhereUsedLine dataclasses."""
    data = payload.get("data", payload)
    records = data.get("records", [])
    return [
        WhereUsedLine(
            parent_item=str(r["PRNO"]).strip(),
            structure_type=str(r.get("STRT", "")).strip(),
            facility=str(r.get("FACI", "")).strip(),
            sequence_number=int(r["MSEQ"]),
            component_number=str(r["MTNO"]).strip(),
            operation_number=int(r["OPNO"]),
            quantity=float(r["CNQT"]),
            unit_of_measure=str(r.get("PEUN", "")).strip(),
            from_date=int(r["FDAT"]),
            to_date=int(r.get("TDAT", _OPEN_ENDED_TDAT)),
        )
        for r in records
    ]
