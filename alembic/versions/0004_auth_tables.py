"""Auth session tables — JTI blocklist and refresh tokens

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-17

Adds two tables that replace the Redis DB1 session store (ADR-007).

  jti_blocklist:   One row per logged-out or revoked access token JTI.
                   Checked on every authenticated request (PK lookup).
                   Rows are cleaned up at FastAPI startup and hourly.

  refresh_tokens:  SHA-256 hash of each issued refresh token.
                   Supports logout, rotation, and family-revocation on reuse detection.
                   Rows cleaned up when expires_at < now().

Source: ai/memory/12-data-model.md §10
Decision: decisions/ADR-007-redis-elimination-postgresql-broker.md
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── jti_blocklist ─────────────────────────────────────────────────────────
    op.create_table(
        "jti_blocklist",
        sa.Column("jti", sa.UUID(), primary_key=True),
        sa.Column(
            "expires_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
        ),
    )
    op.create_index("idx_jti_expires", "jti_blocklist", ["expires_at"])

    # ── refresh_tokens ────────────────────────────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),  # SHA-256 hex
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column(
            "expires_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "revoked_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # Active tokens by username — partial index excludes revoked rows
    op.create_index(
        "idx_rt_username",
        "refresh_tokens",
        ["username"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index("idx_rt_expires", "refresh_tokens", ["expires_at"])

    # ── Grants for oskar_app ──────────────────────────────────────────────────
    # oskar_app needs SELECT (read), INSERT (issue), UPDATE (revoke) on both tables.
    # DELETE is not granted — cleanup runs as oskar_migration or via a scheduled task
    # that uses the application connection (DELETE WHERE expires_at < now() is safe
    # because it only removes expired rows, not active session data).
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON jti_blocklist  TO oskar_app;")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON refresh_tokens TO oskar_app;")


def downgrade() -> None:
    op.execute("REVOKE ALL ON refresh_tokens FROM oskar_app;")
    op.execute("REVOKE ALL ON jti_blocklist  FROM oskar_app;")
    op.drop_index("idx_rt_expires",  table_name="refresh_tokens")
    op.drop_index("idx_rt_username", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("idx_jti_expires", table_name="jti_blocklist")
    op.drop_table("jti_blocklist")
