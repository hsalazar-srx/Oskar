"""Widen movex_outbox.idempotency_key from VARCHAR(100) to VARCHAR(150)
(Slice E, discovered mid-implementation)

_queue_bom_changes_outbox's CHANGE-type keys use the plan-specified format
PDS002MI.{transaction}:{ecn_id}:{bom_change_id}[:close|:add]. With real
UUIDs for ecn_id/bom_change_id (36 chars each) and the longest BOM
transaction name (PDS002MI.UpdateComponent, 24 chars) plus a :close/:add
suffix (6 chars), the worst case is:

    "PDS002MI.UpdateComponent:" + 36 + ":" + 36 + ":close" = 104 chars

— 4 over the existing VARCHAR(100) cap from migration 0001. The existing
alias/routing key formats (PDS002MI.AddOperation:{ecn_id}:{op_id}, etc.)
fit comfortably under 100, so this was never hit before Slice E's
close+add CHANGE-type keys.

Audited (2026-08-10) for other columns this slice's data could plausibly
overflow, to consolidate rather than fix these one at a time:
  - movex_outbox.mi_transaction VARCHAR(50) — longest value used anywhere
    (including this slice's "PDS002MI.UpdateComponent") is 24 chars. Fine.
  - ecn_movex_errors.mi_transaction VARCHAR(50) — same values, same margin. Fine.
  - ecn_bom_changes.component_number / ecn_items.item_number VARCHAR(15) —
    real Movex item numbers (e.g. "LFCONC0001", 10 chars), not Oskar-
    generated composite keys; no slice-introduced growth here. Fine.
  - idempotency_key is not duplicated on any other table.
idempotency_key is the only column genuinely at risk from this slice's
UUID-based composite key format, so this is the only width fix needed.
Widened to 150 for headroom rather than the bare minimum 104, matching how
other VARCHAR columns in this schema carry margin rather than being sized
exactly to today's longest known value.

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-10
"""
from __future__ import annotations

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE movex_outbox ALTER COLUMN idempotency_key TYPE VARCHAR(150)")


def downgrade() -> None:
    op.execute("ALTER TABLE movex_outbox ALTER COLUMN idempotency_key TYPE VARCHAR(100)")
