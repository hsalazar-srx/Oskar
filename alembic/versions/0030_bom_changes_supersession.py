"""ecn_bom_changes supersession extension + bom_circuit_refs (Slice E,
ADR-012 D4/D6)

Extends the existing (skeletal, migration 0001) ecn_bom_changes table with
the old-value/sequence/ref-des/snapshot columns needed for Stargile's
supersession model (D6: CHANGE = close old line + add new date-effective
line; DELETE = close, never physical delete) — does NOT create the table
fresh, ecn_bom_changes already exists from 0001_initial_schema.py.

New bom_circuit_refs table (D4): Stargile's ZECNCIRF (reference designators
/ circuit refs — data M3's native BOM cannot hold) migrates into an
Oskar-owned table, keyed by the ERP line key (facility, parent_item,
structure_type, sequence_number, from_date) per D4's stated key.

NOTE — plan correction (2026-08-07): the Iteration 2 plan text
(ai/tasks/oskar-iteration-2.md) calls this "0028_bom_changes_supersession.py"
— that numbering is stale. 0028 was already taken by Slice D's
bom_comparisons migration (renumbered 2026-08-06), and Slice E0's
0029_outbox_depends_on.py landed on master ahead of this slice. This
migration is therefore 0030, down_revision "0029".

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-07
"""
from __future__ import annotations

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE ecn_bom_changes
            ADD COLUMN sequence_number     INTEGER       NULL,
            ADD COLUMN old_quantity        DECIMAL(17,6) NULL,
            ADD COLUMN old_operation_number INTEGER      NULL,
            ADD COLUMN old_from_date       INTEGER       NULL,
            ADD COLUMN old_to_date         INTEGER       NULL,
            ADD COLUMN circuit_refs_old    JSONB         NULL,
            ADD COLUMN circuit_refs_new    JSONB         NULL,
            ADD COLUMN snapshot_id         UUID          NULL REFERENCES bom_snapshots(id) ON DELETE SET NULL
    """)
    op.execute("""
        COMMENT ON COLUMN ecn_bom_changes.old_from_date IS
            'YYYYMMDD integer. Required for CHANGE/DELETE change_type (validated in service layer, not a CHECK constraint — mirrors from_date''s existing convention) — identifies which live Movex line is being superseded/closed.';
    """)
    op.execute("""
        COMMENT ON COLUMN ecn_bom_changes.snapshot_id IS
            'FK to bom_snapshots (D2) — the ecn_submit-reason snapshot this change line was authored/reviewed against. Populated by workflow.py at submit/resubmit; used by the dc_approve concurrency gate to re-fetch-and-diff (Slice E test_concurrency_gate.py).';
    """)
    op.execute("CREATE INDEX idx_ecn_bom_changes_snapshot ON ecn_bom_changes(snapshot_id);")

    op.execute("""
        CREATE TABLE bom_circuit_refs (
            id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            facility          VARCHAR(3)   NOT NULL,
            parent_item       VARCHAR(15)  NOT NULL,
            structure_type    VARCHAR(3)   NOT NULL DEFAULT '001',
            sequence_number   INTEGER      NOT NULL,
            from_date         INTEGER      NOT NULL,
            to_date           INTEGER      NULL,
            circuit_refs      JSONB        NOT NULL DEFAULT '[]',
            source_ecn        UUID         NULL REFERENCES ecn_instances(id) ON DELETE SET NULL,
            source_system     VARCHAR(20)  NOT NULL DEFAULT 'oskar',
            created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),

            CONSTRAINT uq_bom_circuit_refs_erp_line_key
                UNIQUE (facility, parent_item, structure_type, sequence_number, from_date)
        );
    """)
    op.execute("""
        COMMENT ON TABLE bom_circuit_refs IS
            'Oskar-owned reference-designator store (ADR-012 D4) — migrates Stargile ZECNCIRF, which M3''s native BOM cannot hold. Keyed by the ERP line key. C-1 (GET /api/bom/{prno}/circuit-refs) backfills this table during the Stargile decommission window only; retired after cutover.';
    """)
    op.execute("CREATE INDEX idx_bom_circuit_refs_parent ON bom_circuit_refs(facility, parent_item);")
    op.execute("CREATE INDEX idx_bom_circuit_refs_source_ecn ON bom_circuit_refs(source_ecn) WHERE source_ecn IS NOT NULL;")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bom_circuit_refs;")
    op.execute("DROP INDEX IF EXISTS idx_ecn_bom_changes_snapshot;")
    op.execute("""
        ALTER TABLE ecn_bom_changes
            DROP COLUMN IF EXISTS sequence_number,
            DROP COLUMN IF EXISTS old_quantity,
            DROP COLUMN IF EXISTS old_operation_number,
            DROP COLUMN IF EXISTS old_from_date,
            DROP COLUMN IF EXISTS old_to_date,
            DROP COLUMN IF EXISTS circuit_refs_old,
            DROP COLUMN IF EXISTS circuit_refs_new,
            DROP COLUMN IF EXISTS snapshot_id
    """)
