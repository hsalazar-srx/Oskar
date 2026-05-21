"""Add DELETE to ecn_routing_operations change_type constraint

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-21

PDS002MI.DelOperation exists in the Movex MI API with params:
  Company, Facility, Product Number, Product Structure Type,
  Sequence Number, Operation Number, From Date.

The original constraint (ADD | UPDATE only) was implemented before the
delete path was in scope. Adding DELETE now so engineers can record
routing-step removal intent on an ECN.

For DELETE rows: operation_number identifies the op to remove; run_time
and setup_time are not used by the outbox worker for this change_type
and should be set to 0 by the UI.

ecn_bom_changes already accepts ADD | CHANGE | DELETE — routing_operations
is now consistent with the broader ECN change vocabulary.
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ecn_routing_operations DROP CONSTRAINT ck_routing_change_type")
    op.execute(
        "ALTER TABLE ecn_routing_operations ADD CONSTRAINT ck_routing_change_type "
        "CHECK (change_type IN ('ADD', 'UPDATE', 'DELETE'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE ecn_routing_operations DROP CONSTRAINT ck_routing_change_type")
    op.execute(
        "ALTER TABLE ecn_routing_operations ADD CONSTRAINT ck_routing_change_type "
        "CHECK (change_type IN ('ADD', 'UPDATE'))"
    )
