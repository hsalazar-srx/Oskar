"""Add customer_ecn_refs to ecn_instances and full-text search index.

customer_ecn_refs stores one or more customer-side ECN reference numbers,
comma-separated, as a plain VARCHAR. Nullable — most ECNs won't have one.

The GIN index enables the extended FTS search added in Sprint 6: search now
covers ecn_number, title, description, customer_number, and customer_ecn_refs
rather than only title + ecn_number.

Revision ID: 0017
Revises: 0016
"""

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ecn_instances ADD COLUMN customer_ecn_refs VARCHAR(500)"
    )
    op.execute(
        "COMMENT ON COLUMN ecn_instances.customer_ecn_refs IS "
        "'Comma-separated list of customer ECN reference numbers for cross-referencing.'"
    )
    # Full-text search index covering all searchable text columns.
    # Uses 'simple' dictionary so abbreviations like ECN numbers are not stemmed.
    op.execute(
        """
        CREATE INDEX ecn_fts_idx ON ecn_instances
        USING GIN (
            to_tsvector('simple',
                coalesce(ecn_number, '') || ' ' ||
                coalesce(title, '') || ' ' ||
                coalesce(description, '') || ' ' ||
                coalesce(customer_number, '') || ' ' ||
                coalesce(customer_ecn_refs, '')
            )
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ecn_fts_idx")
    op.execute("ALTER TABLE ecn_instances DROP COLUMN IF EXISTS customer_ecn_refs")
