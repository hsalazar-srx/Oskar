"""ecn_routing_operations table (S2-19)

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-08

Changes:

  New table: ecn_routing_operations
    Stores engineer-authored routing operation deltas for an ECN item.
    At DC_APPROVED the outbox worker compares these rows against the live
    MPDOPE snapshot and issues AddOperation / UpdateOperation MI calls.

  Columns:
    id               UUID PK
    ecn_item_id      FK → ecn_items.id ON DELETE CASCADE
    operation_number INT  (POOPNO — Movex op sequence, col A of Labour Routing template)
    operation_description VARCHAR(30)  (POOPDS — 30-char Movex hard limit)
    work_centre      VARCHAR(8)   (POPLGR)
    run_time         NUMERIC(10,3) (POPITI — minutes)
    setup_time       NUMERIC(10,3) (POSETI — minutes, nullable)
    change_type      VARCHAR(10)  CHECK IN ('ADD', 'UPDATE')
    movex_snapshot   JSONB NULL   (live MPDOPE row at time of pre-flight read)
    created_at       TIMESTAMPTZ  DEFAULT now()
    updated_at       TIMESTAMPTZ  DEFAULT now()

  Constraints:
    UQ (ecn_item_id, operation_number) — one row per op per item
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")

    op.create_table(
        "ecn_routing_operations",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "ecn_item_id",
            sa.UUID(),
            sa.ForeignKey("ecn_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operation_number", sa.Integer(), nullable=False),
        sa.Column("operation_description", sa.String(30), nullable=False),
        sa.Column("work_centre", sa.String(8), nullable=False),
        sa.Column("run_time", sa.Numeric(10, 3), nullable=False),
        sa.Column("setup_time", sa.Numeric(10, 3), nullable=True),
        sa.Column("change_type", sa.String(10), nullable=False),
        sa.Column("movex_snapshot", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("change_type IN ('ADD', 'UPDATE')", name="ck_routing_change_type"),
        sa.UniqueConstraint("ecn_item_id", "operation_number", name="uq_routing_item_opno"),
    )

    op.create_index(
        "ix_routing_ops_ecn_item_id",
        "ecn_routing_operations",
        ["ecn_item_id"],
    )

    # updated_at trigger — reuse the same pattern as other tables
    op.execute("""
        CREATE TRIGGER trg_routing_ops_updated_at
        BEFORE UPDATE ON ecn_routing_operations
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_routing_ops_updated_at ON ecn_routing_operations")
    op.drop_table("ecn_routing_operations")
