"""Create ecn_comments table.

A lightweight, status-unrestricted comment/note thread per ECN. Comments may
be added at any ECN status including CLOSED — this is an explicit requirement
from the engineering team (Sprint 6).

Unlike ecn_transition_history (immutable audit chain), comments are editable
and deletable by their author; DC may delete any comment.

Revision ID: 0018
Revises: 0017
"""

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ecn_comments (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ecn_id          UUID NOT NULL REFERENCES ecn_instances(id) ON DELETE CASCADE,
            author_username VARCHAR(100) NOT NULL,
            body            TEXT NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX ecn_comments_ecn_id_created_at_idx "
        "ON ecn_comments(ecn_id, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ecn_comments")
