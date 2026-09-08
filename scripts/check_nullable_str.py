#!/usr/bin/env python
"""
OSKAR — catch `str(None)` before it reaches the database.

THE BUG THIS EXISTS FOR
-----------------------
A migration makes a column nullable. Somewhere in the service layer a row is
mapped to a dataclass with a bare `str(row[i])`. Nothing raises — `str(None)`
is the perfectly valid string "None" — so the value is written, read back, and
compared against real ids for as long as it takes someone to notice that an
id looks odd.

Two of these appeared while migration 0034 made `ecn_mpns.ecn_item_id`
nullable (ADR-016): `_row_to_mpn` would have produced "None" for a standalone
MPN, and `_queue_alias_outbox` would have written the same into
`movex_outbox`. Both were caught by reading the diff, which is not a control.

HOW IT DETECTS THEM
-------------------
Not by guessing at nullability from column names — that produces false
positives the moment two tables share a column name (verified: three such
matches, all NOT NULL in reality). It uses the signal the codebase already
maintains honestly: the dataclass field annotation.

    @dataclass
    class ECNMPNDetail:
        ecn_item_id: str | None      <-- declared optional

    return ECNMPNDetail(
        ecn_item_id=str(row[1]),     <-- converted unconditionally  ==> BUG
    )

A field declared `X | None` that is assigned a bare `str(...)` in a
constructor call is the exact shape of both bugs, and it needs no database
connection to see.

Guarded forms are recognised and pass:

    str(row[1]) if row[1] is not None else None
    str(row[1]) if row[1] else None
    str(x) if x else None

SECOND SHAPE — SQL BIND PARAMETERS
----------------------------------
The other bug was not a dataclass at all. It was a dict of bind parameters
handed to session.execute():

    {"id": new_id, "item_id": str(item_id), ...}     <-- item_id may be None

There is no annotation to lean on here, so this half uses a narrower rule: a
dict key whose name matches a KNOWN-NULLABLE COLUMN (listed explicitly below,
because guessing from column names alone produces false positives — three
were confirmed, all NOT NULL in reality despite sharing a name with a nullable
column on another table).

The list is deliberately short and manual. It is a place to add a column when
a migration makes it nullable, which is exactly the moment this bug is
introduced — see the checklist in ADR-016.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not flag `str()` on non-Optional fields — those are correct by
construction, and flagging them would train people to ignore the output.
It does not try to prove a value is non-None through control flow; that needs
a type checker, and the annotation is the cheaper 90% signal.

Usage
-----
    python scripts/check_nullable_str.py                  # whole src/ tree
    python scripts/check_nullable_str.py src/services     # a subtree

Exit 0 = clean, 1 = findings. Wired into .pre-commit-config.yaml.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = REPO_ROOT / "src"

# Bind-parameter / dict keys that correspond to a column which IS nullable and
# holds an id. Add to this list whenever a migration makes an id column
# nullable — that is the moment the str(None) bug gets introduced.
#
# Kept explicit rather than derived from information_schema on purpose: this
# check must run with no database (pre-commit, CI, a fresh clone), and a
# name-based lookup across all tables produced false positives where two
# tables share a column name.
NULLABLE_ID_KEYS = frozenset({
    "item_id",       # movex_outbox.ecn_item_id, ecn_mpns/ecn_bom_changes.ecn_item_id
    "ecn_item_id",   # nullable since ADR-014 (BOM) and ADR-016 (MPN)
    "snapshot_id",   # ecn_bom_changes.snapshot_id
    "depends_on",    # movex_outbox.depends_on
    "source_ecn",    # bom_circuit_refs.source_ecn, item_mpns.source_ecn
})


def _is_optional(annotation: ast.expr | None) -> bool:
    """True for `X | None`, `Optional[X]`, `Union[X, None]`."""
    if annotation is None:
        return False

    # X | None  (PEP 604)
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        for side in (annotation.left, annotation.right):
            if isinstance(side, ast.Constant) and side.value is None:
                return True
            if isinstance(side, ast.Name) and side.id == "None":
                return True
        return _is_optional(annotation.left) or _is_optional(annotation.right)

    # Optional[X] / Union[X, None]
    if isinstance(annotation, ast.Subscript):
        base = annotation.value
        name = (
            base.id if isinstance(base, ast.Name)
            else base.attr if isinstance(base, ast.Attribute)
            else None
        )
        if name == "Optional":
            return True
        if name == "Union":
            sl = annotation.slice
            elts = sl.elts if isinstance(sl, ast.Tuple) else [sl]
            return any(isinstance(e, ast.Constant) and e.value is None for e in elts)

    return False


def _collect_optional_fields(tree: ast.Module) -> dict[str, set[str]]:
    """{ClassName: {field names annotated as optional}} for every class."""
    out: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        fields = {
            stmt.target.id
            for stmt in node.body
            if isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and _is_optional(stmt.annotation)
        }
        if fields:
            out[node.name] = fields
    return out


def _is_bare_str_call(node: ast.expr) -> bool:
    """`str(...)` NOT wrapped in a conditional guard."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "str"
    )


def check_file(path: Path, optional_fields: dict[str, set[str]]) -> list[tuple[int, str, str]]:
    """Return [(lineno, ClassName.field, source_line)] for each finding."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()
    findings: list[tuple[int, str, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        cls_name = (
            func.id if isinstance(func, ast.Name)
            else func.attr if isinstance(func, ast.Attribute)
            else None
        )
        if cls_name not in optional_fields:
            continue

        for kw in node.keywords:
            if kw.arg is None or kw.arg not in optional_fields[cls_name]:
                continue
            # An IfExp here IS the guard — `str(x) if x else None` is correct.
            if _is_bare_str_call(kw.value):
                ln = kw.value.lineno
                text = lines[ln - 1].strip() if 0 < ln <= len(lines) else ""
                findings.append((ln, f"{cls_name}.{kw.arg}", text))

    # ── Second shape: dict literals of SQL bind parameters ────────────────
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            if key.value not in NULLABLE_ID_KEYS:
                continue
            if _is_bare_str_call(value):
                ln = value.lineno
                text = lines[ln - 1].strip() if 0 < ln <= len(lines) else ""
                findings.append((ln, f'bind param "{key.value}"', text))

    return findings


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv[1:]] or [DEFAULT_TARGET]

    files: list[Path] = []
    for t in targets:
        if t.is_dir():
            files.extend(sorted(t.rglob("*.py")))
        elif t.suffix == ".py":
            files.append(t)

    # Optional-field declarations are collected across ALL files first: a
    # dataclass in models.py is constructed from items.py, so a per-file view
    # would see neither half of the problem.
    optional_fields: dict[str, set[str]] = {}
    parsed: dict[Path, ast.Module] = {}
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        parsed[f] = tree
        for cls, fields in _collect_optional_fields(tree).items():
            optional_fields.setdefault(cls, set()).update(fields)

    total = 0
    for f in files:
        if f not in parsed:
            continue
        for ln, field, text in check_file(f, optional_fields):
            if total == 0:
                print("Bare str() assigned to an Optional field — str(None) is \"None\":\n")
            rel = f.relative_to(REPO_ROOT) if f.is_relative_to(REPO_ROOT) else f
            print(f"  {rel}:{ln}  {field}")
            print(f"      {text}")
            total += 1

    if total:
        print(
            f"\n{total} finding(s). If the value really can be None, guard it:\n"
            "      str(x) if x is not None else None\n"
            "If it genuinely cannot, the field's annotation is wrong — fix that instead."
        )
        return 1

    print(f"check_nullable_str: {len(files)} file(s), no findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
