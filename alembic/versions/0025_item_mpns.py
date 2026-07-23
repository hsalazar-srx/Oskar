"""item_mpns + manufacturer_synonyms (Slice C, ADR-012 D3 / Decision 8)

New Oskar-owned MPN master, replacing Stargile ZECNMPMS. Keyed like ZECNMPMS
(ITNO, SUNO, MPN) — see `scripts/migrate_zecnmpms.py` for the migration that
loads real ZECNMPMS data through `src/services/bom/zecnmpms_transform.py`.

Two tables:

  item_mpns
    The MPN master itself. `ecn_mpns` (per-ECN staging, migration 0001) stays
    as-is and upserts into this table at the `movex_write_complete` workflow
    transition (src/services/ecn/workflow.py, beside `_queue_alias_outbox`).
    Natural key (item_number, supplier_number, mpn) matches ZECNMPMS so the
    migration script can upsert idempotently. `is_default` + `end_effective_date`
    together express "current default" — enforced live via the partial unique
    index below (service-layer also enforces the date-effective rule when
    setting a new default: see src/services/bom/mpn_master.py).

  manufacturer_synonyms
    Raw manufacturer-string -> canonical-name lookup (Stargile MPTX30 concept
    per ADR-012 — not a PLM live-compare-engine concept). Seeded here from real
    PLM `manufacturer_strings` / `srx_manufacturer_reference_string` data
    (c:\\Projects\\PLM\\PLMServer\\data\\srx_data\\ManufacturerMasterName.csv,
    147 canonical manufacturers / 1045 raw-string variants, deduplicated and
    copied into this repo as alembic/seed_data/manufacturer_synonyms_plm.csv so
    the migration has no runtime dependency on the PLM repo). Canonical names
    are PLM's own stored form (its `master` column — typically upper-case
    legal-entity style, e.g. "STMICROELECTRONICS", "TEXAS INSTRUMENTS
    INCORPORATED") rather than hand-prettified names — faithful to the real
    source rather than invented. `raw_string` is stored upper-cased/trimmed;
    `normalize_manufacturer()` (src/services/bom/mpn_master.py) upper-cases and
    trims its input the same way before lookup, so the PK is the actual lookup
    key. R5 fix-forward: `scripts/add_manufacturer_synonym.py` inserts single
    rows here post-migration without a deploy.

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-23
"""
from __future__ import annotations

import csv
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

_SEED_CSV = Path(__file__).resolve().parent.parent / "seed_data" / "manufacturer_synonyms_plm.csv"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE item_mpns (
            id                     UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            item_number            VARCHAR(15)   NOT NULL,
            supplier_number        VARCHAR(10)   NOT NULL DEFAULT '',
            mpn                    VARCHAR(30)   NOT NULL,
            manufacturer_name      VARCHAR(60),
            manufacturer_canonical VARCHAR(60),
            is_default             BOOLEAN       NOT NULL DEFAULT FALSE,
            end_effective_date     DATE          NULL,
            from_date              DATE          NULL,
            to_date                DATE          NULL,
            source_ecn             UUID          NULL REFERENCES ecn_instances(id) ON DELETE SET NULL,
            price                  DECIMAL(17,6) NULL,
            currency               VARCHAR(3)    NULL,
            moq                    INTEGER       NULL,
            spq                    INTEGER       NULL,
            distributor_number     VARCHAR(15)   NULL,
            distributor_name       VARCHAR(60)   NULL,
            legacy_extra           JSONB         NULL,
            source_system          VARCHAR(20)   NOT NULL DEFAULT 'oskar',
            migrated_at            TIMESTAMPTZ   NULL,
            created_at             TIMESTAMPTZ   NOT NULL DEFAULT now(),
            updated_at             TIMESTAMPTZ   NOT NULL DEFAULT now()
        );
    """)
    op.execute("""
        ALTER TABLE item_mpns
            ADD CONSTRAINT uq_item_mpns_natural_key
            UNIQUE (item_number, supplier_number, mpn);
    """)
    op.execute("""
        CREATE INDEX idx_item_mpns_mpn_pattern ON item_mpns (mpn text_pattern_ops);
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_item_mpns_current_default ON item_mpns (item_number, supplier_number)
            WHERE is_default AND end_effective_date IS NULL;
    """)
    op.execute("CREATE INDEX idx_item_mpns_item_number ON item_mpns (item_number);")

    op.execute("""
        CREATE TABLE manufacturer_synonyms (
            raw_string     VARCHAR(60) PRIMARY KEY,
            canonical_name VARCHAR(60) NOT NULL,
            source         VARCHAR(20) NOT NULL DEFAULT 'manual'
        );
    """)

    _seed_manufacturer_synonyms()


def _seed_manufacturer_synonyms() -> None:
    if not _SEED_CSV.exists():
        return
    conn = op.get_bind()
    table = sa.table(
        "manufacturer_synonyms",
        sa.column("raw_string", sa.String),
        sa.column("canonical_name", sa.String),
        sa.column("source", sa.String),
    )
    with _SEED_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [
            {
                "raw_string": row["raw_string"][:60],
                "canonical_name": row["canonical_name"][:60],
                "source": "plm_migration",
            }
            for row in reader
        ]
    if rows:
        conn.execute(sa.insert(table), rows)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS manufacturer_synonyms;")
    op.execute("DROP INDEX IF EXISTS idx_item_mpns_item_number;")
    op.execute("DROP INDEX IF EXISTS uq_item_mpns_current_default;")
    op.execute("DROP INDEX IF EXISTS idx_item_mpns_mpn_pattern;")
    op.execute("DROP TABLE IF EXISTS item_mpns;")
