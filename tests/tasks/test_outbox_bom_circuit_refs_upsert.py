"""
OSKAR — bom_circuit_refs upsert on AddComponent outbox completion (Slice E,
ADR-012 D4).

_queue_bom_changes_outbox (workflow.py) embeds a _circuit_refs metadata dict
in an AddComponent row's mi_params whenever the source ecn_bom_changes row
carries circuit_refs_new. On successful completion of that outbox entry,
process_outbox_entry upserts bom_circuit_refs — this proves the wiring with
a mocked DB cursor (same strategy as tests/tasks/test_outbox_depends_on.py),
not a real Postgres round-trip (that's the ecn_bom_changes/movex_outbox
integration coverage in test_queue_bom_changes_outbox.py; bom_circuit_refs
itself has no dedicated integration test in this slice since exercising it
would require a live/stubbed MI call succeeding, which W-1 does not support
yet — see I2-19).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from src.tasks.movex_outbox import _upsert_bom_circuit_refs, process_outbox_entry


def _entry(
    outbox_id: str = "ob-add-1",
    ecn_id: str = "ecn-1",
    mi_transaction: str = "PDS002MI.AddComponent",
    mi_params: dict[str, Any] | None = None,
    idempotency_key: str = "PDS002MI.AddComponent:ecn-1:bc-1",
) -> dict[str, Any]:
    return {
        "id": outbox_id,
        "ecn_id": ecn_id,
        "ecn_item_id": None,
        "mi_transaction": mi_transaction,
        "mi_params": mi_params or {"parent_item": "LF100001"},
        "idempotency_key": idempotency_key,
        "state": "pending",
        "attempt_count": 0,
        "max_attempts": 10,
        "next_retry_at": None,
        "last_error": None,
        "depends_on": None,
    }


class TestBomCircuitRefsUpsertOnSuccess:
    def test_add_component_with_circuit_refs_upserts(self) -> None:
        meta = {
            "facility": "L", "parent_item": "LF100001", "structure_type": "001",
            "sequence_number": 10, "from_date": 20260901,
            "circuit_refs": ["R1", "R7"], "source_ecn": "ecn-1",
        }
        entry = _entry(mi_params={
            "parent_item": "LF100001", "component_item": "LF200010",
            "quantity": 4.0, "unit_of_measure": "EA", "operation_number": 10,
            "from_date": 20260901, "bom_type": "M", "facility": "L",
            "_circuit_refs": meta,
        })
        cur = MagicMock()
        cur.fetchone.side_effect = [entry, {"ecn_number": "ECN-2026-L-0001"}, {"pending": 0}]
        cur.fetchall.side_effect = [[], []]
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with (
            patch("src.tasks.movex_outbox._get_conn", return_value=conn),
            patch("src.tasks.movex_outbox._run_mi_call", return_value={"MSID": ""}),
            patch("src.tasks.movex_outbox._upsert_bom_circuit_refs") as mock_upsert,
            patch.object(process_outbox_entry, "apply_async"),
            patch("src.tasks.movex_outbox.advance_ecn_to_implemented"),
        ):
            result = process_outbox_entry("ob-add-1")

        assert result == "completed"
        mock_upsert.assert_called_once()
        called_meta = mock_upsert.call_args[0][1]
        assert called_meta == meta

    def test_delete_component_close_row_does_not_upsert(self) -> None:
        """PDS002MI.Delete close rows (I2-19) never carry _circuit_refs — no-op."""
        entry = _entry(
            mi_transaction="PDS002MI.Delete",
            idempotency_key="PDS002MI.Delete:ecn-1:bc-1:close",
            mi_params={
                "parent_item": "LF100001", "component_item": "LF200010",
                "operation_number": 10, "from_date": 20240101,
                "bom_type": "M", "facility": "L",
            },
        )
        cur = MagicMock()
        cur.fetchone.side_effect = [entry, {"ecn_number": "ECN-2026-L-0001"}, {"pending": 0}]
        cur.fetchall.side_effect = [[], []]
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with (
            patch("src.tasks.movex_outbox._get_conn", return_value=conn),
            patch("src.tasks.movex_outbox._run_mi_call", return_value={"success": True, "data": {"MSID": "000"}}),
            patch("src.tasks.movex_outbox._upsert_bom_circuit_refs") as mock_upsert,
            patch.object(process_outbox_entry, "apply_async"),
            patch("src.tasks.movex_outbox.advance_ecn_to_implemented"),
        ):
            result = process_outbox_entry("ob-add-1")

        assert result == "completed"
        mock_upsert.assert_not_called()

    def test_add_component_without_circuit_refs_does_not_upsert(self) -> None:
        """A plain ADD whose ecn_bom_changes row has no circuit_refs_new —
        the common case — must not call the upsert at all."""
        entry = _entry(mi_params={
            "parent_item": "LF100001", "component_item": "LF200010",
            "quantity": 4.0, "unit_of_measure": "EA", "operation_number": 10,
            "from_date": 20260901, "bom_type": "M", "facility": "L",
        })
        cur = MagicMock()
        cur.fetchone.side_effect = [entry, {"ecn_number": "ECN-2026-L-0001"}, {"pending": 0}]
        cur.fetchall.side_effect = [[], []]
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with (
            patch("src.tasks.movex_outbox._get_conn", return_value=conn),
            patch("src.tasks.movex_outbox._run_mi_call", return_value={"MSID": ""}),
            patch("src.tasks.movex_outbox._upsert_bom_circuit_refs") as mock_upsert,
            patch.object(process_outbox_entry, "apply_async"),
            patch("src.tasks.movex_outbox.advance_ecn_to_implemented"),
        ):
            result = process_outbox_entry("ob-add-1")

        assert result == "completed"
        mock_upsert.assert_not_called()


class TestUpsertBomCircuitRefsSql:
    def test_executes_insert_with_expected_params(self) -> None:
        cur = MagicMock()
        meta = {
            "facility": "L", "parent_item": "LF100001", "structure_type": "001",
            "sequence_number": 10, "from_date": 20260901,
            "circuit_refs": ["R1", "R7"], "source_ecn": "ecn-1",
        }
        _upsert_bom_circuit_refs(cur, meta)

        cur.execute.assert_called_once()
        sql, params = cur.execute.call_args[0]
        assert "INSERT INTO bom_circuit_refs" in sql
        assert "ON CONFLICT" in sql
        assert params[1] == "L"          # facility
        assert params[2] == "LF100001"   # parent_item
        assert params[3] == "001"        # structure_type
        assert params[4] == 10           # sequence_number
        assert params[5] == 20260901     # from_date
        assert params[7] == "ecn-1"      # source_ecn

    def test_structure_type_defaults_to_001_when_missing(self) -> None:
        cur = MagicMock()
        meta = {
            "facility": "L", "parent_item": "LF100001",
            "sequence_number": 10, "from_date": 20260901,
            "circuit_refs": [], "source_ecn": None,
        }
        _upsert_bom_circuit_refs(cur, meta)

        params = cur.execute.call_args[0][1]
        assert params[3] == "001"
