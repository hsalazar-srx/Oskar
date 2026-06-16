"""Add customer_number to ecn_instances

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-16

Adds a header-level customer_number column, required for new ECNs going forward
(enforced at the application layer in ECNCreateBody — not a DB constraint, since
existing rows must remain valid with NULL).

This drives the `cuno` value used by GET /api/v1/parts/suggest-pn (see
src/routers/parts.py) — one ECN = one customer, set once at creation and never
edited (changing it after items already have suggested part numbers would desync
the embedded code from the ECN's actual customer).

VARCHAR(10), not VARCHAR(2): real Movex customer codes (OCUSMA.OKCUNO, confirmed
live against CRS610) are 4-digit numeric (e.g. '0021'). The 2-char value 'AC' is a
fixed placeholder for generic/common stock items not tied to a specific customer —
see ai/memory/02-movex-erp-authority.md §10.
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ecn_instances ADD COLUMN customer_number VARCHAR(10)")
    op.execute(
        "COMMENT ON COLUMN ecn_instances.customer_number IS "
        "'PN-embedding customer code — either a real OCUSMA.OKCUNO value or the "
        "fixed generic-stock marker AC. Drives Suggest PN cuno.'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE ecn_instances DROP COLUMN IF EXISTS customer_number")
