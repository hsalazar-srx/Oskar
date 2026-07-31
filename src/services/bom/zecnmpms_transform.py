"""
OSKAR — ZECNMPMS -> item_mpns transform (Slice C).

Pure module (no DB, no I/O) implementing step 2 of the ZECNMPMS migration
plan (ai/tasks/oskar-iteration-2.md): TRIM; uppercase ITNO/MPZMANPN;
0/99999999 dates -> NULL; MPZDEFFL '1' -> true; YYYYMMDD -> DATE; MPTX30 ->
canonical via manufacturer_synonyms (miss -> raw + review file); leftover
columns -> legacy_extra JSONB; source_system='zecnmpms'.

Consumed by both scripts/migrate_zecnmpms.py (--input csv) and its --from-api
mode (M-1 stub/real endpoint — same raw-dict row shape either way, since M-1
serves untransformed ZECNMPMS columns per the contract doc).

Row shape in: a dict of raw ZECNMPMS columns (str keys/values, as produced by
csv.DictReader or the M-1 JSON response). Column names verified 2026-07-27
against the real Stargile source (c:/Projects/SuperTool/Stargile_Source_Code/
workspace/Startronics/DataModels/ECN/Maintenance/{MPMDetail,MPMBrowse}.cml) —
the field names originally used here (MPN, MPPRIC, MPMOQ, MPCURR, MPSPQ) were
inferred while drafting ADR-012/the Iteration 2 plan, not verified, and were
wrong: the real columns are MPZMANPN, MPMPRC, MPZMPMOQ, MPCUCD, MPZMPSPQ.
MPDIST/MPDISTNM never existed on ZECNMPMS at all — invented with no source;
item_mpns.distributor_number/distributor_name stay NULL for zecnmpms-origin
rows and are populated by a future Iteration 3 supplier-chain source instead.
Mapped columns: ITNO, SUNO, MPZMANPN, MPTX30, MPZDEFFL, MPFDAT, MPTDAT,
MPMPRC, MPCUCD, MPZMPMOQ, MPZMPSPQ. Real columns with no dedicated item_mpns
field (MPZEEFDT effective date, MPZECNID originating ECN, MPZCAWID/MPZREWID
cancellation/reschedule windows, MPZMNCNR NCNR flag, MPLMDT/MPLMTM last-
modified, MPCONO, MPFACI) fall through to legacy_extra like any other
unmapped column — no special-casing needed.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Mapping

from src.services.bom.mpn_master import normalize_manufacturer

# Sentinel date values used throughout Stargile/Movex numeric-date fields —
# 0 = "never set", 99999999 = "open ended" — both mean "no date" here.
_SENTINEL_DATES = {0, 99999999}

# Columns explicitly mapped to first-class item_mpns fields. Anything else in
# the raw row (MPZEEFDT, MPZECNID, MPLMDT, etc. — see module docstring) falls
# through to legacy_extra.
_MAPPED_COLUMNS = {
    "ITNO", "SUNO", "MPZMANPN", "MPTX30", "MPZDEFFL", "MPFDAT", "MPTDAT",
    "MPMPRC", "MPCUCD", "MPZMPMOQ", "MPZMPSPQ",
}


@dataclass(frozen=True)
class TransformedRow:
    item_number: str
    supplier_number: str
    mpn: str
    manufacturer_name: str | None       # raw MPTX30, trimmed, original case
    manufacturer_canonical: str | None  # normalize_manufacturer() result
    manufacturer_miss: bool             # True = no synonym matched (review file)
    is_default: bool
    from_date: datetime.date | None
    to_date: datetime.date | None
    price: float | None
    currency: str | None
    moq: int | None
    spq: int | None
    distributor_number: str | None
    distributor_name: str | None
    legacy_extra: dict
    source_system: str = "zecnmpms"


@dataclass(frozen=True)
class DuplicateCollapse:
    """A natural key that appeared more than once in the source extract.

    Per the migration plan step 3 (idempotent upsert on the natural key) and
    step 4 (duplicate-key collapse report): the last occurrence in input order
    wins — this is a documented judgment call (the M-1 export's row ordering
    isn't guaranteed chronological, so "last wins" is a reasonable default,
    not a verified "most recent" guarantee). Every collision is reported so
    the migration operator can review before/after cutover.
    """
    natural_key: tuple[str, str, str]
    occurrences: int


@dataclass(frozen=True)
class DefaultFlagViolation:
    """More than one MPN marked is_default=True for the same (item, supplier)
    after natural-key collapse — a Stargile data-quality issue, not something
    this transform silently "fixes". Reported per the migration plan step 4
    ("default-flag violations (resolve manually)"). The load step still
    proceeds (upsert_item_mpn's built-in demotion means the last-processed
    default wins, matching "last occurrence wins" above) but this is flagged
    so a human confirms that's the right outcome.
    """
    item_number: str
    supplier_number: str
    mpn_count: int


@dataclass(frozen=True)
class TransformBatchResult:
    rows: list[TransformedRow]
    duplicate_collapses: list[DuplicateCollapse]
    manufacturer_misses: list[str]
    default_flag_violations: list[DefaultFlagViolation]


def natural_key(row: TransformedRow) -> tuple[str, str, str]:
    return (row.item_number, row.supplier_number, row.mpn)


def _clean_str(raw: object) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def _parse_date(raw: object) -> datetime.date | None:
    s = _clean_str(raw)
    if s is None:
        return None
    value = int(s)
    if value in _SENTINEL_DATES:
        return None
    s8 = f"{value:08d}"
    return datetime.date(int(s8[0:4]), int(s8[4:6]), int(s8[6:8]))


def _parse_float(raw: object) -> float | None:
    s = _clean_str(raw)
    return float(s) if s is not None else None


def _parse_int(raw: object) -> int | None:
    s = _clean_str(raw)
    return int(float(s)) if s is not None else None


def transform_row(raw_in: Mapping[str, object], synonyms: Mapping[str, str]) -> TransformedRow:
    # Normalise every key to uppercase up front. The CSV path already uses
    # uppercase headers (no-op here); the real M-1 endpoint returns lowercase
    # keys ("itno", "mpzmanpn", ...) and, on this endpoint specifically, one
    # mixed-case key ("mptX30") — verified live 2026-08-03. str.upper()
    # handles any input casing uniformly without special-casing the quirk.
    raw = {k.upper(): v for k, v in raw_in.items()}

    item_number = (_clean_str(raw.get("ITNO")) or "").upper()
    supplier_number = _clean_str(raw.get("SUNO")) or ""
    mpn = (_clean_str(raw.get("MPZMANPN")) or "").upper()

    manufacturer_name = _clean_str(raw.get("MPTX30"))
    norm = normalize_manufacturer(manufacturer_name, synonyms)
    manufacturer_canonical = norm.canonical or None
    manufacturer_miss = norm.matched is False and manufacturer_name is not None

    is_default = _clean_str(raw.get("MPZDEFFL")) == "1"

    legacy_extra = {
        k: v for k, v in raw.items()
        if k not in _MAPPED_COLUMNS and v not in (None, "")
    }

    return TransformedRow(
        item_number=item_number,
        supplier_number=supplier_number,
        mpn=mpn,
        manufacturer_name=manufacturer_name,
        manufacturer_canonical=manufacturer_canonical,
        manufacturer_miss=manufacturer_miss,
        is_default=is_default,
        from_date=_parse_date(raw.get("MPFDAT")),
        to_date=_parse_date(raw.get("MPTDAT")),
        price=_parse_float(raw.get("MPMPRC")),
        currency=_clean_str(raw.get("MPCUCD")),
        moq=_parse_int(raw.get("MPZMPMOQ")),
        spq=_parse_int(raw.get("MPZMPSPQ")),
        distributor_number=None,  # ZECNMPMS has no distributor columns — see module docstring
        distributor_name=None,
        legacy_extra=legacy_extra,
        source_system="zecnmpms",
    )


def transform_batch(
    raw_rows: list[Mapping[str, object]], synonyms: Mapping[str, str]
) -> TransformBatchResult:
    by_key: dict[tuple[str, str, str], TransformedRow] = {}
    occurrence_counts: dict[tuple[str, str, str], int] = {}
    misses: set[str] = set()

    for raw in raw_rows:
        row = transform_row(raw, synonyms)
        key = natural_key(row)
        occurrence_counts[key] = occurrence_counts.get(key, 0) + 1
        by_key[key] = row  # last occurrence wins — see DuplicateCollapse docstring
        if row.manufacturer_miss and row.manufacturer_name:
            misses.add(row.manufacturer_name)

    duplicate_collapses = sorted(
        (
            DuplicateCollapse(natural_key=key, occurrences=count)
            for key, count in occurrence_counts.items()
            if count > 1
        ),
        key=lambda d: d.natural_key,
    )

    default_counts: dict[tuple[str, str], int] = {}
    for row in by_key.values():
        if row.is_default:
            group_key = (row.item_number, row.supplier_number)
            default_counts[group_key] = default_counts.get(group_key, 0) + 1

    default_flag_violations = sorted(
        (
            DefaultFlagViolation(item_number=item, supplier_number=supplier, mpn_count=count)
            for (item, supplier), count in default_counts.items()
            if count > 1
        ),
        key=lambda v: (v.item_number, v.supplier_number),
    )

    return TransformBatchResult(
        rows=list(by_key.values()),
        duplicate_collapses=duplicate_collapses,
        manufacturer_misses=sorted(misses),
        default_flag_violations=default_flag_violations,
    )
