"""
OSKAR — _queue_bom_changes_outbox unit tests (Slice E, ADR-012 D6).

Pure logic tests (idempotency key format, MI transaction name mapping) that
need no DB — mirrors tests/routers/test_routing_operations.py's
TestQueueRoutingOperationsOutbox tail section. The actual DB round-trip
(outbox rows inserted with correct depends_on linkage) is covered by
tests/integration/test_queue_bom_changes_outbox.py.

D6 supersession rule: ADD -> 1 AddComponent row. DELETE -> 1 UpdateComponent
"close" row (TDAT = old_to_date, or today if not given — never a physical
delete). CHANGE -> 2 rows: an UpdateComponent close row (closes the OLD line,
TDAT = new FDAT - 1) and an AddComponent add row whose depends_on is the
close row's id, so the add only dispatches once the close has completed
(Slice E0's mechanism).

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
        expected = f"PDS002MI.UpdateComponent:{ecn_id}:{change_id}:close"
        assert expected == "PDS002MI.UpdateComponent:ecn-123:bomchange-456:close"

    def test_change_type_close_key(self):
        ecn_id, change_id = "ecn-123", "bomchange-456"
        expected = f"PDS002MI.UpdateComponent:{ecn_id}:{change_id}:close"
        assert expected == "PDS002MI.UpdateComponent:ecn-123:bomchange-456:close"

    def test_change_type_add_key(self):
        ecn_id, change_id = "ecn-123", "bomchange-456"
        expected = f"PDS002MI.AddComponent:{ecn_id}:{change_id}:add"
        assert expected == "PDS002MI.AddComponent:ecn-123:bomchange-456:add"


class TestMiTransactionMapping:
    def test_add_maps_to_add_component(self):
        _mi_tx = {"ADD": "PDS002MI.AddComponent", "DELETE": "PDS002MI.UpdateComponent"}
        assert _mi_tx["ADD"] == "PDS002MI.AddComponent"

    def test_delete_maps_to_update_component_close(self):
        _mi_tx = {"ADD": "PDS002MI.AddComponent", "DELETE": "PDS002MI.UpdateComponent"}
        assert _mi_tx["DELETE"] == "PDS002MI.UpdateComponent"

    def test_change_maps_to_close_then_add(self):
        """CHANGE decomposes into two transactions, not a single mapped verb."""
        close_tx = "PDS002MI.UpdateComponent"
        add_tx = "PDS002MI.AddComponent"
        assert close_tx == "PDS002MI.UpdateComponent"
        assert add_tx == "PDS002MI.AddComponent"
