"""bom_comparisons (Slice D, ADR-012 D5)

Persists a saved compare run for save/history (GET /api/v1/bom/comparisons/{id}
and its /export endpoint, src/routers/bom.py). Sides are DESCRIPTORS
({type: erp|snapshot|upload, ...identifying fields}), never a local BOM
mirror — the plan is explicit no local BOM mirror exists anywhere in Oskar
(BOM reads always go through movex-rest-api or a bom_snapshots row); a saved
comparison re-describes WHERE its two sides came from, not a frozen copy of
the lines themselves (comparison_result already carries the diffed lines via
compare.py's BOMDiff-shaped JSONB, so there is no need to duplicate them a
second time inside the descriptor).

comparison_result stores compare.py's BOMDiff serialised to the NEXUS-style
JSONB shape ({added, removed, changed, unresolved, stats}) — see
src/routers/bom.py for the serialisation (dataclasses -> dict at the router
boundary, matching the rest of Oskar's Pydantic-response-model convention;
compare.py itself has no JSON-encoding concerns, staying pure).

cost_impact/risk_flags are nullable — Slice D does not populate them (no
costing/risk-scoring logic exists yet); the columns exist now so a later
slice (Iteration 3 costing intelligence, or an earlier Slice E BOM-scrub
overlap) can populate them without a further migration.

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-04

Renumbered 2026-08-06 alongside 0027_bom_snapshots.py — see that file's
docstring for why.
"""
from __future__ import annotations

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE bom_comparisons (
            id                  UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            left_descriptor     JSONB         NOT NULL,
            right_descriptor    JSONB         NOT NULL,
            comparison_result   JSONB         NOT NULL,
            cost_impact         DECIMAL(17,6) NULL,
            risk_flags          TEXT[]        NOT NULL DEFAULT '{}',
            created_by          VARCHAR(100)  NOT NULL,
            created_at          TIMESTAMPTZ   NOT NULL DEFAULT now()
        );
    """)
    op.execute("""
        CREATE INDEX idx_bom_comparisons_created_at ON bom_comparisons (created_at DESC);
    """)
    op.execute("""
        CREATE INDEX idx_bom_comparisons_created_by ON bom_comparisons (created_by);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bom_comparisons;")
