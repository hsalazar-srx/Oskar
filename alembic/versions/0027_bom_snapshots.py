"""bom_snapshots (Slice D, ADR-012 D2)

Point-in-time JSONB line array + SHA-256 content hash. Serves three
consumers per D2: comparison inputs (Slice D, this migration's own scope),
ECN concurrency baseline (Slice E, dc_approve re-fetch-and-diff), and history
(browsable snapshot list). Only `compare`/`manual` reasons are populated by
Slice D; `ecn_submit` is a later slice's concern (Slice E, snapshot at
submit/resubmit) but the schema/reason enum supports it now so Slice E does
not need its own migration to add a value to an already-shipped enum.

Retention (ADR-012 Decision 7, 2026-07-20): reason=ecn_submit rows are kept
indefinitely (the audit trail of what a DC actually approved against);
compare/manual rows are pruned after 90 days. This migration creates the
table/index only — the pruning job itself is out of Slice D's scope (no
retention-sweep task exists yet in this migration; a later slice adds it).

content_hash is computed application-side (src/services/bom/snapshots.py)
over a canonicalised (key-order-independent) JSON encoding of `lines` so two
snapshots capturing the identical line set hash identically regardless of
dict key ordering or line ordering in the source payload.

ecn_id is nullable (a compare/manual snapshot is not tied to any ECN) with
ON DELETE SET NULL — deleting an ECN must not cascade-delete its submit
snapshots (the D2 "audit trail" reason those exist at all).

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-04

Renumbered 2026-08-06: originally authored as 0026 in an isolated worktree
(claude/oskar-bom-slice-d) branched before 0026_ecn_comments_soft_delete.py
landed on master via a separate, concurrent line of work. Collision caught
before this revision was ever safely applied — see 0026_ecn_comments_soft_delete.py
for the unrelated migration that keeps the original 0026 slot.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE bom_snapshots (
            id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            item_number     VARCHAR(15)   NOT NULL,
            facility        VARCHAR(5)    NOT NULL,
            structure_type  VARCHAR(3)    NOT NULL DEFAULT '001',
            level_mode      VARCHAR(10)   NOT NULL DEFAULT 'single',
            lines           JSONB         NOT NULL,
            line_count      INTEGER       NOT NULL,
            content_hash    CHAR(64)      NOT NULL,
            reason          VARCHAR(20)   NOT NULL,
            ecn_id          UUID          NULL REFERENCES ecn_instances(id) ON DELETE SET NULL,
            captured_by     VARCHAR(100)  NOT NULL,
            captured_at     TIMESTAMPTZ   NOT NULL DEFAULT now()
        );
    """)
    op.execute("""
        ALTER TABLE bom_snapshots
            ADD CONSTRAINT ck_bom_snapshots_level_mode
            CHECK (level_mode IN ('single', 'indented'));
    """)
    op.execute("""
        ALTER TABLE bom_snapshots
            ADD CONSTRAINT ck_bom_snapshots_reason
            CHECK (reason IN ('ecn_submit', 'compare', 'manual'));
    """)
    op.execute("""
        CREATE INDEX idx_bom_snapshots_item_number ON bom_snapshots (item_number, facility);
    """)
    op.execute("""
        CREATE INDEX idx_bom_snapshots_ecn_id ON bom_snapshots (ecn_id) WHERE ecn_id IS NOT NULL;
    """)
    op.execute("""
        CREATE INDEX idx_bom_snapshots_content_hash ON bom_snapshots (content_hash);
    """)
    op.execute("""
        CREATE INDEX idx_bom_snapshots_reason_captured_at ON bom_snapshots (reason, captured_at);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bom_snapshots;")
