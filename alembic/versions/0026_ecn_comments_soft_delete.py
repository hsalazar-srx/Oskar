"""Soft-delete for ecn_comments.

Deletes become an UPDATE (deleted_at/deleted_by) instead of a hard DELETE, so
a "History" view can show what was removed and by whom. The existing
ecn_comments_ecn_id_created_at_idx (migration 0018) stays as-is — it backs the
History view's full-list query (include_deleted=true). This adds a partial
index scoped to the active-only query, which is the default and far more
frequent read path.

Revision ID: 0026
Revises: 0025
"""

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ecn_comments "
        "ADD COLUMN deleted_at TIMESTAMPTZ, "
        "ADD COLUMN deleted_by VARCHAR(100)"
    )
    op.execute(
        "CREATE INDEX ecn_comments_ecn_id_active_idx "
        "ON ecn_comments(ecn_id, created_at) WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ecn_comments_ecn_id_active_idx")
    op.execute(
        "ALTER TABLE ecn_comments "
        "DROP COLUMN IF EXISTS deleted_at, "
        "DROP COLUMN IF EXISTS deleted_by"
    )
