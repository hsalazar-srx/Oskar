"""
OSKAR — tests for scripts/check_nullable_str.py

The check is enforcement code: it blocks commits. If it produces false
positives people will disable it, and if it misses the bug it exists for it is
worse than nothing because it implies coverage that is not there.

Both fixture cases below are the REAL bugs found while migration 0034 made
ecn_mpns.ecn_item_id nullable (ADR-016), reduced to the smallest code that
reproduces each shape:

  1. dataclass field declared `str | None`, assigned a bare str(...)
  2. SQL bind-parameter dict keyed on a nullable id column, same

Everything else asserts it stays quiet — guarded forms, non-Optional fields,
and unrelated str() calls.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHECKER = REPO_ROOT / "scripts" / "check_nullable_str.py"


def run_checker(target: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(CHECKER), str(target)],
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def write(tmp_path: Path, name: str, source: str) -> Path:
    d = tmp_path / "src"
    d.mkdir(exist_ok=True)
    (d / name).write_text(source, encoding="utf-8")
    return d


class TestCatchesTheDataclassShape:
    """Bug 1 — _row_to_mpn before the ADR-016 fix."""

    def test_bare_str_on_optional_field_is_flagged(self, tmp_path: Path):
        target = write(tmp_path, "m.py", '''
from dataclasses import dataclass

@dataclass
class Detail:
    id: str
    ecn_item_id: str | None

def build(row):
    return Detail(id=str(row[0]), ecn_item_id=str(row[1]))
''')
        code, out = run_checker(target)
        assert code == 1
        assert "Detail.ecn_item_id" in out
        # The non-Optional `id` must NOT be flagged — str() there is correct.
        assert "Detail.id" not in out

    def test_optional_via_typing_Optional_is_flagged(self, tmp_path: Path):
        target = write(tmp_path, "m.py", '''
from dataclasses import dataclass
from typing import Optional

@dataclass
class Detail:
    ecn_item_id: Optional[str]

def build(row):
    return Detail(ecn_item_id=str(row[1]))
''')
        code, out = run_checker(target)
        assert code == 1
        assert "Detail.ecn_item_id" in out

    @pytest.mark.parametrize(
        "guard",
        [
            "str(row[1]) if row[1] is not None else None",
            "str(row[1]) if row[1] else None",
        ],
    )
    def test_guarded_forms_pass(self, tmp_path: Path, guard: str):
        """Both styles appear in the codebase; neither may be flagged, or the
        check becomes noise people learn to skip."""
        target = write(tmp_path, "m.py", f'''
from dataclasses import dataclass

@dataclass
class Detail:
    ecn_item_id: str | None

def build(row):
    return Detail(ecn_item_id={guard})
''')
        code, out = run_checker(target)
        assert code == 0, out


class TestCatchesTheBindParamShape:
    """Bug 2 — _queue_alias_outbox before the ADR-016 fix."""

    def test_bare_str_on_nullable_id_bind_param_is_flagged(self, tmp_path: Path):
        target = write(tmp_path, "w.py", '''
async def queue(session, new_id, ecn_id, item_id):
    await session.execute(
        "INSERT INTO movex_outbox (id, ecn_id, ecn_item_id) VALUES (:id, :ecn_id, :item_id)",
        {"id": new_id, "ecn_id": ecn_id, "item_id": str(item_id)},
    )
''')
        code, out = run_checker(target)
        assert code == 1
        assert 'bind param "item_id"' in out

    def test_guarded_bind_param_passes(self, tmp_path: Path):
        target = write(tmp_path, "w.py", '''
async def queue(session, new_id, ecn_id, item_id):
    await session.execute(
        "INSERT INTO movex_outbox (id, ecn_id, ecn_item_id) VALUES (:id, :ecn_id, :item_id)",
        {"id": new_id, "item_id": str(item_id) if item_id is not None else None},
    )
''')
        code, out = run_checker(target)
        assert code == 0, out

    def test_unlisted_key_is_not_flagged(self, tmp_path: Path):
        """Only keys in NULLABLE_ID_KEYS are checked. Flagging every str() in
        every dict would bury the real signal."""
        target = write(tmp_path, "w.py", '''
async def queue(session, ecn_id):
    await session.execute("...", {"ecn_id": str(ecn_id)})
''')
        code, out = run_checker(target)
        assert code == 0, out


class TestNoFalsePositives:
    def test_plain_str_calls_are_ignored(self, tmp_path: Path):
        target = write(tmp_path, "p.py", '''
def render(value, other):
    label = str(value)
    return label + str(other)
''')
        code, out = run_checker(target)
        assert code == 0, out

    def test_non_optional_field_is_ignored(self, tmp_path: Path):
        target = write(tmp_path, "p.py", '''
from dataclasses import dataclass

@dataclass
class Detail:
    id: str

def build(row):
    return Detail(id=str(row[0]))
''')
        code, out = run_checker(target)
        assert code == 0, out


class TestRealCodebase:
    def test_src_tree_is_clean(self):
        """The whole point: src/ must stay clean, so a regression is a failing
        test and not just a pre-commit message someone can skip with -n."""
        code, out = run_checker(REPO_ROOT / "src")
        assert code == 0, out
