"""
OSKAR — src.services.bom.compare — comparison engine (Slice D, ADR-012 D5).

Pure, zero-I/O module. diff_boms() takes two lists of plain line dicts and a
CompareOptions and returns a BOMDiff. Reused by three callers (D5): rev-vs-
rev ERP compare, customer-BOM compare (I2-2, src/services/bom/customer_bom.py),
and ECN concurrency detection (I2-6, a later slice) — that's why lines are
plain dict[str, Any] rather than a fixed dataclass: the three callers have
genuinely different field sets (ERP lines carry component_number/
operation_number/quantity/...; customer-BOM lines carry ipn/cpn/mpn[]/mfr[]/
designator/description/quantity; a fixed shape would force one caller's
irrelevant fields onto the others). Field names are caller-defined strings —
compare.py doesn't know or care what they mean, except for the specific
handling documented below for quantity-like and array-valued fields.

Matching is by KEY, not by line position (parity with PLM's own key-based
compare — see ai/tasks/oskar-iteration-2.md Context: "Comparison Key is
dynamic — any field present in both loaded BOMs"). A BOM whose lines were
simply re-ordered/resequenced but otherwise unchanged diffs as "no changes":
diff_boms builds a key -> [lines] index of `right` up front and looks up each
`left` line by key, so a line at position 5 on the left can match its
counterpart at position 30 on the right. When the SAME key value appears
more than once on the SAME side (e.g. two lines that happen to collide on
whatever key fields the caller chose), each occurrence is still matched
independently, in encounter order, against the other side's remaining
unmatched candidates for that key — a documented, deterministic tie-break
for same-key duplicates, not a claim that "line N on the left corresponds to
line N on the right" in general.

"Op-moved" lines (D5's test list: "...qty/op-moved/uom/effectivity/ref-des
changes"): whether an operation_number change surfaces as a CHANGED line or
as a remove+add pair depends entirely on whether operation_number is part of
the active match key. With the ERP-vs-ERP default key
("component_number", "operation_number"), a line whose op moved has no
counterpart at its old key value, so it is, correctly, a remove+add — the
line's identity in Stargile/M3 terms (MSEQ within an operation) actually did
change. To see op-moves as CHANGED lines instead, the caller selects a key
that does NOT include operation_number (e.g. key=("component_number",)) —
then operation_number becomes an ordinary diffable field and a moved op
shows up as one changed line with a field_changes entry for
"operation_number". Both configurations are exercised in
tests/services/bom/test_compare.py; compare.py does not hardcode which one
is "the" op-moved behaviour because that is a caller-level (dynamic key
selection) decision, not an engine-level one.

Design choices, each fixing one of the three PLM defects named in ADR-012
Decision 9 (see ai/tasks/oskar-iteration-2.md Slice D and Context):

(a) Array-key derivation (MPN/MFR multi-value lines). PLM derives the match
    key from array-valued fields inconsistently (verified against source,
    ADR-012 Context) — this silently breaks matching on multi-value lines.
    Oskar's rule: any key field whose value is a list is normalised via
    _normalise_key_value's array branch on BOTH sides, every time — sort the
    (case-folded) elements, join with '|'. Same function, same call site, for
    every line on both sides: there is no second code path to drift out of
    sync with the first.

(b) Quantity diffing. PLM uses parseFloat-based comparison, so two identical
    non-numeric quantities compare as changed (NaN !== NaN is JS's answer,
    always true). Oskar's rule (_values_equal): try to parse both sides as
    float; if both parse, compare numerically (so "10" == "10.0" == 10).
    If either side fails to parse, fall back to trimmed-string equality
    instead of ever comparing a float to NaN — two non-numeric values that
    are textually equal (e.g. two "N/A" cells) compare as EQUAL, not
    "changed against itself" the way PLM's engine does.

(c) Case-sensitivity. PLM is case-insensitive for MPN/MFR/Designator and
    case-sensitive for everything else (a real inconsistency, not a
    documented design choice, per ADR-012 Context). Oskar picks ONE rule for
    every field, including the match key itself: case-INSENSITIVE string
    comparison everywhere (values upper-cased before comparing/hashing). See
    tests/services/bom/test_compare.py module docstring for the rationale
    (extending the more-permissive existing PLM rule uniformly, since
    MPN/MFR/Designator are exactly the fields most likely to carry
    inconsistent human-entered casing across two BOM sources).

Match key: CompareOptions.key defaults to ("component_number",
"operation_number") — the ERP-vs-ERP default (D5) — with Stargile padding-
equivalence baked into _normalise_key_value's numeric branch so "10" ==
"0010" (OPNO/MSEQ pad-4, per D5; padding-equivalence is really just "compare
numerically when the field looks numeric", so no field-name-specific padding
table is needed here). For uploads/customer-BOM compare, callers pass any
tuple of field names present on both sides (dynamic key selection, parity
with PLM's header-intersection approach) — compare.py has no hardcoded
IPN/CPN/MPN list.

fields=None (CompareOptions default) diffs every field name that appears on
ANY line of either side, excluding the key fields themselves (a key field is
by definition how two lines were matched, not something to report as
"changed" between them). Passing an explicit fields list is Oskar's single
per-field toggle (D5): the same list controls both which fields participate
in the diff AND which fields the caller should render in the result table —
there is no separate "visibility" concept for compare.py to expose, unifying
PLM's Options-modal/column-click split at the data layer.

`unresolved` on BOMDiff exists so the return shape matches the NEXUS-style
JSONB the plan specifies ({added, removed, changed, unresolved, stats}) —
diff_boms() itself never populates it (a pure key/value diff has nothing to
be "unresolved" about; that's a customer_bom.py-level concept — a line that
can't be matched to any item at all via CPN alias or MPN lookup, which is a
resolution failure that happens BEFORE diff_boms ever runs). It is always []
coming out of this module; customer_bom.py's wrapper populates it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_DEFAULT_KEY = ("component_number", "operation_number")


@dataclass(frozen=True)
class CompareOptions:
    key: tuple[str, ...] = _DEFAULT_KEY
    fields: tuple[str, ...] | None = None


@dataclass(frozen=True)
class FieldChange:
    field: str
    old_value: Any
    new_value: Any


@dataclass(frozen=True)
class ChangedLine:
    key: tuple[Any, ...]
    left: dict[str, Any]
    right: dict[str, Any]
    field_changes: list[FieldChange]


@dataclass(frozen=True)
class UnresolvedLine:
    side: str  # "left" | "right"
    line: dict[str, Any]
    reason: str


@dataclass(frozen=True)
class BOMDiffStats:
    left_count: int
    right_count: int
    added_count: int
    removed_count: int
    changed_count: int
    unresolved_count: int


@dataclass(frozen=True)
class BOMDiff:
    added: list[dict[str, Any]]
    removed: list[dict[str, Any]]
    changed: list[ChangedLine]
    unresolved: list[UnresolvedLine]
    stats: BOMDiffStats


def _fold_case(value: str) -> str:
    return value.strip().upper()


def _normalise_key_value(value: Any) -> Any:
    """One consistent normalisation rule for a single key-field value,
    applied identically to every line on both sides (see module docstring,
    defect (a) and (c)).

    - list/tuple (array-valued field, e.g. MPN/MFR): case-folded, sorted,
      joined — order-independent, case-insensitive.
    - numeric-looking string/int/float: normalised through float() so
      "10" == "0010" == 10 (Stargile padding equivalence, D5).
    - anything else: case-folded string.
    """
    if isinstance(value, (list, tuple)):
        return "|".join(sorted(_fold_case(str(v)) for v in value))
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value) if value is not None else ""
    try:
        return float(text.strip())
    except ValueError:
        return _fold_case(text)


def _line_key(line: dict[str, Any], key_fields: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(_normalise_key_value(line.get(f)) for f in key_fields)


def _try_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _values_equal(a: Any, b: Any) -> bool:
    """One consistent equality rule for a single field value (see module
    docstring, defects (b) and (c)).

    Array-valued fields use the same order-independent/case-insensitive rule
    as key derivation. Quantity-like values are compared numerically when
    BOTH sides parse as a number; if either side fails to parse, compare as
    trimmed/case-folded strings instead — never a float-vs-NaN comparison,
    so two equal non-numeric values (e.g. two "N/A" cells) compare equal
    rather than PLM's always-changed defect.
    """
    if isinstance(a, (list, tuple)) or isinstance(b, (list, tuple)):
        a_list = a if isinstance(a, (list, tuple)) else [a]
        b_list = b if isinstance(b, (list, tuple)) else [b]
        return _normalise_key_value(a_list) == _normalise_key_value(b_list)

    if isinstance(a, bool) or isinstance(b, bool):
        return a == b

    a_num = _try_float(a)
    b_num = _try_float(b)
    if a_num is not None and b_num is not None:
        return a_num == b_num

    a_text = _fold_case(str(a)) if a is not None else ""
    b_text = _fold_case(str(b)) if b is not None else ""
    return a_text == b_text


def _diffable_fields(
    left: dict[str, Any],
    right: dict[str, Any],
    key_fields: tuple[str, ...],
    explicit: tuple[str, ...] | None,
) -> list[str]:
    if explicit is not None:
        return [f for f in explicit if f not in key_fields]
    seen: dict[str, None] = {}
    for f in (*left.keys(), *right.keys()):
        if f not in key_fields:
            seen[f] = None
    return list(seen.keys())


def diff_boms(
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
    *,
    opts: CompareOptions | None = None,
) -> BOMDiff:
    """Diff two flat line lists keyed by opts.key. Matching is key-based, not
    positional — see module docstring.

    Deterministic ordering: added/removed/changed are all sorted by their
    match key (tuple comparison) before return, so two runs over the same
    input always produce byte-identical output — required for content-hash-
    stable snapshots (Slice D bom_snapshots) and lets tests assert exact
    list equality rather than "same elements in any order".

    A component repeated at multiple positions on the SAME side is not
    deduplicated: every left line gets its own lookup and, at most, one
    right-side match (consumed so a given right line can never be matched
    twice). single_level.json's LF200010-at-two-operation_numbers fixture
    isn't actually a same-key collision under the default key (the two rows
    differ by operation_number, so they get two distinct keys and match
    independently) — TestSameKeyDuplicatesOnBothSides covers the case where
    the chosen key genuinely collides more than once on a side. This is the
    direct fix for defect (a): PLM's inconsistent array-key derivation
    silently drops/merges multi-value lines; Oskar's per-line independent
    matching means duplicates are only ever "the same line" when the full
    key genuinely matches on both value AND count.
    """
    opts = opts or CompareOptions()
    key_fields = opts.key

    right_by_key: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for line in right:
        right_by_key.setdefault(_line_key(line, key_fields), []).append(line)

    matched_right_ids: set[int] = set()
    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    changed: list[ChangedLine] = []

    for l_line in left:
        l_key = _line_key(l_line, key_fields)
        candidates = right_by_key.get(l_key, [])
        r_line = next((c for c in candidates if id(c) not in matched_right_ids), None)
        if r_line is None:
            removed.append(l_line)
            continue
        matched_right_ids.add(id(r_line))

        diffable = _diffable_fields(l_line, r_line, key_fields, opts.fields)
        field_changes = [
            FieldChange(field=f, old_value=l_line.get(f), new_value=r_line.get(f))
            for f in diffable
            if not _values_equal(l_line.get(f), r_line.get(f))
        ]
        if field_changes:
            changed.append(
                ChangedLine(key=l_key, left=l_line, right=r_line, field_changes=field_changes)
            )

    for r_line in right:
        if id(r_line) not in matched_right_ids:
            added.append(r_line)

    added.sort(key=lambda ln: _line_key(ln, key_fields))
    removed.sort(key=lambda ln: _line_key(ln, key_fields))
    changed.sort(key=lambda c: c.key)

    stats = BOMDiffStats(
        left_count=len(left),
        right_count=len(right),
        added_count=len(added),
        removed_count=len(removed),
        changed_count=len(changed),
        unresolved_count=0,
    )

    return BOMDiff(added=added, removed=removed, changed=changed, unresolved=[], stats=stats)
