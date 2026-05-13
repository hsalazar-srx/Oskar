"""supplier_part_cache table (S3-3)

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-13

Changes:

  New table: supplier_part_cache
    Local PostgreSQL cache for supplier API responses.
    Keyed by MPN. TTL enforced in application layer (SUPPLIER_CACHE_TTL_DAYS, default 30).

    Lookup chain: DigiKey → Nexar → (stubs, Iteration 3)
    A cache hit costs 0 API calls regardless of which supplier originally found the part.

  Columns:
    mpn            TEXT PK              — manufacturer part number (lookup key)
    supplier_id    TEXT NOT NULL        — 'digikey' | 'nexar' | future suppliers
    description    TEXT NOT NULL        — product description (→ ecn_items.item_name)
    manufacturer   TEXT NOT NULL DEFAULT ''
    category       TEXT NOT NULL DEFAULT ''
    lifecycle      TEXT NOT NULL DEFAULT ''
    raw_json       JSONB NULL           — full API response retained for Iteration 3 use
    cached_at      TIMESTAMPTZ NOT NULL DEFAULT now()

  Index:
    idx_supplier_part_cache_cached_at — supports TTL expiry queries
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------


def upgrade() -> None:
    op.create_table(
        "supplier_part_cache",
        sa.Column("mpn", sa.Text(), nullable=False),
        sa.Column("supplier_id", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("manufacturer", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.Text(), nullable=False, server_default=""),
        sa.Column("lifecycle", sa.Text(), nullable=False, server_default=""),
        sa.Column("raw_json", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "cached_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("mpn"),
    )
    op.create_index(
        "idx_supplier_part_cache_cached_at",
        "supplier_part_cache",
        ["cached_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_supplier_part_cache_cached_at", table_name="supplier_part_cache")
    op.drop_table("supplier_part_cache")
