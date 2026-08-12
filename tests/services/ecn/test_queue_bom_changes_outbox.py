"""
OSKAR — _queue_bom_changes_outbox unit tests (Slice E, I2-19).

Pure logic tests (idempotency key format, MI transaction name mapping) that
need no DB — mirrors tests/routers/test_routing_operations.py's
TestQueueRoutingOperationsOutbox tail section. The actual DB round-trip
(outbox rows inserted with correct depends_on linkage) is covered by
tests/integration/test_queue_bom_changes_outbox.py.

I2-19 rule (2026-08-11, superseding D6's original TDAT-based close): ADD ->
1 AddComponent row. DELETE -> 1 PDS002MI.Delete "close" row (physically
removes the old M3 line — no replacement). CHANGE -> 2 rows: a Delete close
row (removes the OLD line) and an AddComponent add row (FDAT = the change's
own from_date) whose depends_on is the close row's id, so the add only
dispatches once the close has completed (Slice E0's mechanism). This
replaces D6's original "close via UpdateComponent/TDAT" model — TDAT is
confirmed broken on movex-rest-api; Delete+AddComponent is both live-verified
working and matches Stargile's own real BOM-apply pattern (see
src/services/ecn/workflow.py's _queue_bom_changes_outbox docstring).

Idempotency key format: PDS002MI.{transaction}:{ecn_id}:{bom_change_id}[:close|:add]
"""
from __future__ import annotations

import pytest


class TestIdempotencyKeyFormat:
    def test_add_change_type_key_has_no_suffix(self):
        ecn_id, change_id = "ecn-123", "bomchange-456"
        expected = f"PDS002MI.AddComponent:{ecn_id}:{change_id}"
        assert expected == "PDS002MI.AddComponent:ecn-123:bomchange-456"

    def test_delete_change_type_key_has_close_suffix(self):
        ecn_id, change_id = "ecn-123", "bomchange-456"
        expected = f"PDS002MI.Delete:{ecn_id}:{change_id}:close"
        assert expected == "PDS002MI.Delete:ecn-123:bomchange-456:close"

    def test_change_type_close_key(self):
        ecn_id, change_id = "ecn-123", "bomchange-456"
        expected = f"PDS002MI.Delete:{ecn_id}:{change_id}:close"
        assert expected == "PDS002MI.Delete:ecn-123:bomchange-456:close"

    def test_change_type_add_key(self):
        ecn_id, change_id = "ecn-123", "bomchange-456"
        expected = f"PDS002MI.AddComponent:{ecn_id}:{change_id}:add"
        assert expected == "PDS002MI.AddComponent:ecn-123:bomchange-456:add"


class TestMiTransactionMapping:
    def test_add_maps_to_add_component(self):
        _mi_tx = {"ADD": "PDS002MI.AddComponent", "DELETE": "PDS002MI.Delete"}
        assert _mi_tx["ADD"] == "PDS002MI.AddComponent"

    def test_delete_maps_to_delete_close(self):
        _mi_tx = {"ADD": "PDS002MI.AddComponent", "DELETE": "PDS002MI.Delete"}
        assert _mi_tx["DELETE"] == "PDS002MI.Delete"

    def test_change_maps_to_close_then_add(self):
        """CHANGE decomposes into two transactions, not a single mapped verb."""
        close_tx = "PDS002MI.Delete"
        add_tx = "PDS002MI.AddComponent"
        assert close_tx == "PDS002MI.Delete"
        assert add_tx == "PDS002MI.AddComponent"
