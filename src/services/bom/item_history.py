"""OSKAR — src.services.bom.item_history — per-item ECN history
(Slice F, I2-12; Stargile ECNChangesBrowse parity).

Answers, for ONE item number: "every ECN that has ever touched this part, and
how". Stargile surfaced this as ECNChangesBrowse; engineers use it before
authoring a change, to see what has already been done to a part and by whom.

An item can be touched in four structurally different ways, and the whole
value of this view is that they are shown TOGETHER — each is a different
table, and a user checking only one would draw the wrong conclusion:

  1. ITEM      — ecn_items row: the item master itself changed (description,
                 procurement group, lead time, ...).
  2. BOM_PARENT— ecn_bom_changes where this item is the PARENT: its own BOM
                 gained, lost or altered a component.
  3. BOM_COMPONENT — ecn_bom_changes where this item is the COMPONENT: it was
                 added to, removed from, or altered within someone else's
                 BOM. This is the one most easily missed, and the one that
                 explains "why did my part's usage change when no ECN names
                 it?".
  4. MPN       — ecn_mpns row: a manufacturer part number was added or
                 changed against this item.

Rows come back newest-first by the ECN's creation time, each carrying enough
ECN header context (number, title, status, originator) to be actionable
without a second lookup.

Read-only and derived — no new tables. Deliberately a single UNION ALL query
rather than four round trips: the four sources are always wanted together,
and paging them independently would make "newest first across all types"
impossible to express.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

CHANGE_ITEM = "ITEM"
CHANGE_BOM_PARENT = "BOM_PARENT"
CHANGE_BOM_COMPONENT = "BOM_COMPONENT"
CHANGE_MPN = "MPN"


@dataclass
class ItemECNHistoryEntry:
    """One way one ECN touched one item.

    A single ECN can produce several entries — e.g. it changed the item
    master AND added two components to its BOM. They are separate rows
    because they are separate facts; collapsing them per ECN would hide
    exactly the detail this view exists to show.
    """

    ecn_id: str
    ecn_number: str
    ecn_title: str
    ecn_status: int
    originator_username: str
    facility: str
    created_at: datetime
    change_type: str          # ITEM | BOM_PARENT | BOM_COMPONENT | MPN
    detail: str               # human-readable summary of what changed
    related_item: str | None  # the OTHER item in a BOM relationship


# One UNION ALL over the four sources. Each branch projects the same column
# list so the result is directly orderable across types.
#
# `related_item` is the counterpart in a BOM relationship: for BOM_PARENT it
# is the component that changed; for BOM_COMPONENT it is the parent whose BOM
# changed. NULL for ITEM and MPN, which have no counterpart.
_HISTORY_SQL = sa.text("""
WITH history AS (
    -- 1. The item master itself changed
    SELECT
        e.id            AS ecn_id,
        e.ecn_number    AS ecn_number,
        e.title         AS ecn_title,
        e.status        AS ecn_status,
        e.originator_username,
        e.facility      AS facility,
        e.created_at    AS created_at,
        'ITEM'          AS change_type,
        COALESCE(
            NULLIF(CONCAT_WS(', ',
                CASE WHEN i.is_new_item THEN 'New item' END,
                NULLIF(i.item_name, ''),
                CASE WHEN i.revision_number IS NOT NULL
                     THEN CONCAT('rev ', i.revision_number) END
            ), ''),
            'Item master change'
        )               AS detail,
        NULL::varchar   AS related_item
    FROM ecn_items i
    JOIN ecn_instances e ON e.id = i.ecn_id
    WHERE i.item_number = :item_number

    UNION ALL

    -- 2. This item's own BOM changed
    SELECT
        e.id, e.ecn_number, e.title, e.status, e.originator_username,
        e.facility, e.created_at,
        'BOM_PARENT',
        CONCAT(b.change_type, ' component ', b.component_number),
        b.component_number
    FROM ecn_bom_changes b
    JOIN ecn_instances e ON e.id = b.ecn_id
    WHERE b.parent_item_number = :item_number

    UNION ALL

    -- 3. This item was changed INSIDE someone else's BOM — the case a user
    --    checking only the item's own records would never see.
    SELECT
        e.id, e.ecn_number, e.title, e.status, e.originator_username,
        e.facility, e.created_at,
        'BOM_COMPONENT',
        CONCAT(b.change_type, ' in BOM of ', b.parent_item_number),
        b.parent_item_number
    FROM ecn_bom_changes b
    JOIN ecn_instances e ON e.id = b.ecn_id
    WHERE b.component_number = :item_number

    UNION ALL

    -- 4. An MPN was added or changed against this item. ecn_mpns reaches its
    --    ECN only through ecn_items (it has no ecn_id of its own), so this
    --    branch joins through the item row.
    SELECT
        e.id, e.ecn_number, e.title, e.status, e.originator_username,
        e.facility, e.created_at,
        'MPN',
        CONCAT('MPN ', m.mpn,
               CASE WHEN m.manufacturer IS NOT NULL AND m.manufacturer <> ''
                    THEN CONCAT(' (', m.manufacturer, ')') ELSE '' END,
               CASE WHEN m.is_default THEN ' [default]' ELSE '' END),
        NULL::varchar
    FROM ecn_mpns m
    JOIN ecn_items i  ON i.id = m.ecn_item_id
    JOIN ecn_instances e ON e.id = i.ecn_id
    WHERE i.item_number = :item_number
)
SELECT * FROM history
ORDER BY created_at DESC, ecn_number DESC, change_type
LIMIT :limit OFFSET :offset
""")

_COUNT_SQL = sa.text("""
SELECT
    (SELECT COUNT(*) FROM ecn_items WHERE item_number = :item_number)
  + (SELECT COUNT(*) FROM ecn_bom_changes WHERE parent_item_number = :item_number)
  + (SELECT COUNT(*) FROM ecn_bom_changes WHERE component_number = :item_number)
  + (SELECT COUNT(*) FROM ecn_mpns m JOIN ecn_items i ON i.id = m.ecn_item_id
     WHERE i.item_number = :item_number)
""")


async def get_item_ecn_history(
    session: AsyncSession,
    item_number: str,
    *,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[ItemECNHistoryEntry], int]:
    """Every ECN that has touched `item_number`, newest first.

    Returns (entries, total). An item with no history returns ([], 0) — that
    is a legitimate answer for a part nobody has changed, not a 404.
    """
    cleaned = item_number.strip()
    params = {"item_number": cleaned, "limit": limit, "offset": offset}

    rows = await session.execute(_HISTORY_SQL, params)
    entries = [
        ItemECNHistoryEntry(
            ecn_id=str(r.ecn_id),
            ecn_number=r.ecn_number,
            ecn_title=r.ecn_title,
            ecn_status=r.ecn_status,
            originator_username=r.originator_username,
            facility=r.facility,
            created_at=r.created_at,
            change_type=r.change_type,
            detail=r.detail,
            related_item=r.related_item,
        )
        for r in rows.fetchall()
    ]

    total_row = await session.execute(_COUNT_SQL, {"item_number": cleaned})
    total = int(total_row.scalar() or 0)

    return entries, total
