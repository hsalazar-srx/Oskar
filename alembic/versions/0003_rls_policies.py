"""Row-Level Security — INSERT-only enforcement on audit tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-16

Applies RLS to the two append-only audit tables so that oskar_app can never
UPDATE or DELETE audit rows — even if application code contains a bug.

  ecn_role_assignments:    INSERT + SELECT only for oskar_app
  ecn_transition_history:  INSERT + SELECT only for oskar_app (SHA-256 audit chain)

Source: ai/memory/12-data-model.md §9

IMPORTANT: These statements run as oskar_migration (ALL ON SCHEMA public).
oskar_app must be created before this migration runs — use scripts/setup-server-secrets.sh.

No data is modified by this migration.
"""
from __future__ import annotations

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ecn_role_assignments — INSERT-only for oskar_app ──────────────────
    # RLS is enabled; UPDATE and DELETE are revoked.
    # SELECT and INSERT remain (role assignments must be read and created by the app).
    op.execute("ALTER TABLE ecn_role_assignments ENABLE ROW LEVEL SECURITY;")
    op.execute("REVOKE UPDATE, DELETE ON ecn_role_assignments FROM oskar_app;")

    # ── ecn_transition_history — INSERT+SELECT only for oskar_app ─────────
    # Full REVOKE then selective GRANT ensures no UPDATE or DELETE can slip through.
    # This enforces the SHA-256 audit chain at the database layer (ADR-004).
    op.execute("ALTER TABLE ecn_transition_history ENABLE ROW LEVEL SECURITY;")
    op.execute("REVOKE ALL ON ecn_transition_history FROM oskar_app;")
    op.execute("GRANT INSERT, SELECT ON ecn_transition_history TO oskar_app;")


def downgrade() -> None:
    # Restore full oskar_app access and disable RLS
    op.execute("GRANT ALL ON ecn_transition_history TO oskar_app;")
    op.execute("ALTER TABLE ecn_transition_history DISABLE ROW LEVEL SECURITY;")

    op.execute("GRANT UPDATE, DELETE ON ecn_role_assignments TO oskar_app;")
    op.execute("ALTER TABLE ecn_role_assignments DISABLE ROW LEVEL SECURITY;")
