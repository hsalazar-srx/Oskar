"""movex_outbox.depends_on (Slice E0, ADR-012 Decision 3)

Core dispatch-engine change, not BOM-specific: every ECN write path
(aliases, routing ops, and Slice E's BOM writes) shares movex_outbox and
process_outbox_entry. depends_on lets one outbox entry declare it must not
be dispatched until another entry (any mi_transaction, not just BOM) has
completed — needed by Slice E's CHANGE-type BOM writes (close old line,
then add new line, in that order) but built and tested here against the
*existing* alias/routing dispatch paths first, per ADR-012 Decision 3, so a
bug in the core ordering mechanism is caught in isolation.

ON DELETE SET NULL: if a dependency row is ever deleted (outbox rows are
never deleted in normal operation, but nothing guarantees it structurally),
the dependent should not have its own row cascade-deleted or start
referencing a nonexistent id — process_outbox_entry's dependency-state
lookup treats a missing/NULL depends_on the same as "no dependency", so
falling back to unconditional dispatch is the safe default, not a silent
hang.

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-06
"""
from __future__ import annotations

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE movex_outbox
        ADD COLUMN depends_on UUID NULL REFERENCES movex_outbox(id) ON DELETE SET NULL
    """)
    op.execute("""
        CREATE INDEX idx_outbox_depends_on
        ON movex_outbox(depends_on)
        WHERE depends_on IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_outbox_depends_on")
    op.execute("ALTER TABLE movex_outbox DROP COLUMN IF EXISTS depends_on")
