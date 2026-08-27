"""supplier_part_cache split into descriptive and commercial field classes
(Iteration 3 — licensing exposure + price staleness)

Two independent reasons the single 30-day TTL from migration 0010 is wrong:

1. LICENSING. Verified against primary sources 2026-08-27:
   - DigiKey user agreement §5.1(e) prohibits using the API "to update or
     create your own database of information"
     (https://developer.digikey.com/api-user-agreement) — quoted verbatim.
   - Octopart/Nexar cap caching at 24 hours.
   - Element14 and Arrow carry near-identical anti-caching clauses.

   A 30-day persistent store of price and stock is the worst-exposed shape
   of this. Descriptive data (what a part IS) is a materially weaker claim
   than commercial data (what it COSTS today), so the two are separated and
   the commercial half is held for hours, not weeks.

   This migration does not by itself make Oskar compliant — see
   docs/supplier-api-landscape.md §3. It removes the indefensible part
   (month-old pricing in a permanent table) while a written variance is
   sought. It is a mitigation, not a resolution.

2. CORRECTNESS, independent of the above. 30-day-old pricing is simply
   wrong, and stock is wrong within hours, while descriptions are stable for
   years. One TTL cannot be right for both.

Changes:
  - NEW commercial_json JSONB NULL      — price/stock only
  - NEW commercial_cached_at TIMESTAMPTZ NULL — its own independent clock
  - raw_json is RE-SCOPED to descriptive fields only. Existing rows are
    scrubbed of the commercial keys in place (see below) rather than
    dropped, so descriptive cache warmth survives the migration.

On the backfill: existing raw_json blobs are the whole adapter payload,
price included. They are rewritten to remove the commercial keys. No
existing row gets commercial_json populated — that data is deliberately
discarded rather than carried over, because its age is unknown and by
definition older than the new 24h ceiling. Callers re-fetch on next lookup.

Revision ID: 0033
Revises: 0032
Create Date: 2026-08-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

# Keys moved out of raw_json. Kept in sync with COMMERCIAL_FIELDS in
# src/adapters/suppliers/chain.py — that module is the source of truth for
# the classification; this list exists only to scrub already-stored rows.
_COMMERCIAL_KEYS = ("unit_price", "quantity_available", "price_breaks", "moq", "currency")

# ---------------------------------------------------------------------------


def upgrade() -> None:
    op.add_column(
        "supplier_part_cache",
        sa.Column("commercial_json", sa.dialects.postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "supplier_part_cache",
        sa.Column("commercial_cached_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # Strip commercial keys out of every existing raw_json blob. `- text[]`
    # removes keys from a jsonb object and is a no-op for keys that are not
    # present, so this is safe for rows written by any adapter.
    #
    # The ARRAY[...]::text[] cast is required, not cosmetic: passing a Python
    # list as a plain bind parameter makes asyncpg reject it ("expected str,
    # got list") because the jsonb - text[] operator gives it no type to infer
    # from. Caught by running this migration, not by review.
    op.execute(
        sa.text(
            "UPDATE supplier_part_cache "
            "SET raw_json = raw_json - CAST(:keys AS text[]) "
            "WHERE raw_json IS NOT NULL"
        ).bindparams(sa.bindparam("keys", value=list(_COMMERCIAL_KEYS)))
    )

    # Supports the commercial-staleness predicate without scanning.
    op.create_index(
        "idx_supplier_part_cache_commercial_cached_at",
        "supplier_part_cache",
        ["commercial_cached_at"],
    )


def downgrade() -> None:
    # Commercial data is NOT merged back into raw_json — doing so would
    # recreate the exact persistent price store this migration exists to
    # remove, and a downgrade is not a reason to reintroduce a terms problem.
    op.drop_index(
        "idx_supplier_part_cache_commercial_cached_at",
        table_name="supplier_part_cache",
    )
    op.drop_column("supplier_part_cache", "commercial_cached_at")
    op.drop_column("supplier_part_cache", "commercial_json")
