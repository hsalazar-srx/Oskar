"""
OSKAR — src.services.bom.explode unit tests (Slice B, ADR-012)

Pure unit tests — no DB/HTTP. multi_level.json / where_used.json are loaded
directly from tests/fixtures/bom/ (the same golden fixtures FakeERPAdapter and
scripts/movex_stub.py serve), per the plan's "Pure unit (no DB/HTTP): ...
explode math" TDD-mechanics bucket.

multi_level.json shape (3 levels, one phantom, one repeated component):
  LEVL1 LF100001 -> LF300001 (MSEQ10, qty 1.0)
  LEVL2 LF300001 -> LF200010 (MSEQ10, qty 2.0)
  LEVL2 LF300001 -> LF400001 (MSEQ20, qty 1.0, ITTY=9 phantom)
  LEVL3 LF400001 -> LF200011 (MSEQ10, qty 4.0)
  LEVL3 LF400001 -> LF200012 (MSEQ20, qty 1.0)
  LEVL1 LF100001 -> LF200010 (MSEQ20, qty 3.0)   <- LF200010 repeated at a 2nd
  LEVL1 LF100001 -> LF200014 (MSEQ30, qty 1.0)       tree position (roll-up case)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services.bom.explode import assemble_where_used, build_bom_tree, rollup_quantities
from src.services.bom.models import BOMCycleError

_FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "bom"


def _load_records(filename: str) -> list[dict]:
    payload = json.loads((_FIXTURES_DIR / filename).read_text())
    return payload["data"]["records"]


class TestBuildBomTree:
    def test_root_matches_requested_item_number(self):
        records = _load_records("multi_level.json")

        root = build_bom_tree("LF100001", records)

        assert root.component_number == "LF100001"

    def test_direct_children_match_level_1_records_in_order(self):
        records = _load_records("multi_level.json")

        root = build_bom_tree("LF100001", records)

        assert [c.component_number for c in root.children] == ["LF300001", "LF200010", "LF200014"]

    def test_grandchildren_assembled_under_correct_parent(self):
        records = _load_records("multi_level.json")

        root = build_bom_tree("LF100001", records)
        subassembly = next(c for c in root.children if c.component_number == "LF300001")

        assert [c.component_number for c in subassembly.children] == ["LF200010", "LF400001"]

    def test_great_grandchildren_assembled_under_phantom(self):
        records = _load_records("multi_level.json")

        root = build_bom_tree("LF100001", records)
        subassembly = next(c for c in root.children if c.component_number == "LF300001")
        phantom = next(c for c in subassembly.children if c.component_number == "LF400001")

        assert [c.component_number for c in phantom.children] == ["LF200011", "LF200012"]

    def test_leaf_nodes_have_no_children(self):
        records = _load_records("multi_level.json")

        root = build_bom_tree("LF100001", records)
        leaf = next(c for c in root.children if c.component_number == "LF200014")

        assert leaf.children == []


class TestPhantomDetection:
    def test_itty_9_flagged_as_phantom(self):
        records = _load_records("multi_level.json")

        root = build_bom_tree("LF100001", records)
        subassembly = next(c for c in root.children if c.component_number == "LF300001")
        phantom = next(c for c in subassembly.children if c.component_number == "LF400001")

        assert phantom.is_phantom is True

    def test_itty_3_not_flagged_as_phantom(self):
        records = _load_records("multi_level.json")

        root = build_bom_tree("LF100001", records)
        real_component = next(c for c in root.children if c.component_number == "LF200010")

        assert real_component.is_phantom is False


class TestCumulativeQuantityRollup:
    def test_cumulative_quantity_extends_through_ancestor_chain(self):
        """LF200011 sits 3 levels deep under LF100001 -> LF300001(qty1) ->
        LF400001(qty1) -> LF200011(qty4): cumulative = 1*1*4 = 4."""
        records = _load_records("multi_level.json")

        root = build_bom_tree("LF100001", records)
        subassembly = next(c for c in root.children if c.component_number == "LF300001")
        phantom = next(c for c in subassembly.children if c.component_number == "LF400001")
        capacitor = next(c for c in phantom.children if c.component_number == "LF200011")

        assert capacitor.cumulative_quantity == 4.0

    def test_repeated_component_has_independent_cumulative_quantity_per_position(self):
        records = _load_records("multi_level.json")

        root = build_bom_tree("LF100001", records)
        subassembly = next(c for c in root.children if c.component_number == "LF300001")
        resistor_under_subassembly = next(c for c in subassembly.children if c.component_number == "LF200010")
        resistor_top_level = next(c for c in root.children if c.component_number == "LF200010")

        assert resistor_under_subassembly.cumulative_quantity == 2.0
        assert resistor_top_level.cumulative_quantity == 3.0

    def test_rollup_quantities_sums_repeated_component_across_tree_positions(self):
        """LF200010 appears at two tree positions (cumulative 2.0 and 3.0) —
        the multi_level.json fixture is specifically built to exercise this."""
        records = _load_records("multi_level.json")

        root = build_bom_tree("LF100001", records)
        totals = rollup_quantities(root)

        assert totals["LF200010"] == 5.0

    def test_rollup_excludes_root_and_includes_every_other_component_once_per_position(self):
        records = _load_records("multi_level.json")

        root = build_bom_tree("LF100001", records)
        totals = rollup_quantities(root)

        assert "LF100001" not in totals
        assert totals["LF300001"] == 1.0
        assert totals["LF400001"] == 1.0
        assert totals["LF200011"] == 4.0
        assert totals["LF200012"] == 1.0
        assert totals["LF200014"] == 1.0


class TestCycleGuard:
    def test_self_referencing_component_raises_bom_cycle_error(self):
        records = [
            {"PRNO": "LF100001", "MSEQ": 10, "MTNO": "LF100001", "ITDS": "Self-reference",
             "OPNO": 10, "CNQT": 1.0},
        ]

        with pytest.raises(BOMCycleError):
            build_bom_tree("LF100001", records)

    def test_indirect_cycle_raises_bom_cycle_error(self):
        records = [
            {"PRNO": "LF100001", "MSEQ": 10, "MTNO": "LF200001", "ITDS": "A", "OPNO": 10, "CNQT": 1.0},
            {"PRNO": "LF200001", "MSEQ": 10, "MTNO": "LF100001", "ITDS": "cycles back to root",
             "OPNO": 10, "CNQT": 1.0},
        ]

        with pytest.raises(BOMCycleError):
            build_bom_tree("LF100001", records)

    def test_max_depth_exceeded_raises_bom_cycle_error(self):
        # A long linear chain with no real cycle but deeper than max_depth —
        # treated the same way (a well-formed BOM never needs to recurse past
        # the depth cap; exceeding it is itself the failure signal).
        records = [
            {"PRNO": f"LF{i:06d}", "MSEQ": 10, "MTNO": f"LF{i + 1:06d}", "ITDS": "chain",
             "OPNO": 10, "CNQT": 1.0}
            for i in range(20)
        ]

        with pytest.raises(BOMCycleError):
            build_bom_tree("LF000000", records, max_depth=5)

    def test_well_formed_deep_tree_within_max_depth_does_not_raise(self):
        records = [
            {"PRNO": f"LF{i:06d}", "MSEQ": 10, "MTNO": f"LF{i + 1:06d}", "ITDS": "chain",
             "OPNO": 10, "CNQT": 1.0}
            for i in range(5)
        ]

        root = build_bom_tree("LF000000", records, max_depth=12)

        assert root.component_number == "LF000000"


class TestAssembleWhereUsed:
    def test_maps_records_to_where_used_lines(self):
        payload = json.loads((_FIXTURES_DIR / "where_used.json").read_text())

        lines = assemble_where_used(payload)

        assert len(lines) == 2
        assert lines[0].parent_item == "LF100001"
        assert lines[0].component_number == "LF200010"
        assert lines[0].quantity == 3.0
        assert lines[1].parent_item == "LF300001"
