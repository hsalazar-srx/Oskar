"""
OSKAR — movex_outbox dispatch wiring for PDS002MI.Delete / AddComponent
(Slice E BOM writes, I2-19).

I2-19 (2026-08-11): the original design closed BOM lines via
PDS002MI.UpdateComponent (TDAT). That transaction's TDAT field is confirmed
broken on movex-rest-api (reports success, never persists). Per the
movex-rest-api team's own suggestion, confirmed against Stargile's real
source (Stargile's live BOM-apply engine never used UpdateComponent/TDAT for
BOM lines either — see workflow.py's _queue_bom_changes_outbox docstring),
Oskar now closes lines via PDS002MI.Delete instead, which is live-verified
working. UpdateComponent is no longer on _dispatch_mi_call's dispatch table
at all — these tests confirm Delete dispatches correctly and that
UpdateComponent, if it ever reached dispatch by mistake (e.g. a stale
mi_transaction string left over from before this change), fails loudly as
an unknown transaction rather than silently resolving to something else.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.tasks.movex_outbox import _dispatch_mi_call


class TestDeleteComponentDispatch:
    @pytest.mark.asyncio
    async def test_delete_dispatches_to_delete_bom_component(self):
        """PDS002MI.Delete (I2-19's close mechanism for both DELETE and the
        close-half of CHANGE) must resolve to delete_bom_component."""
        with patch("src.adapters.erp.movex.MovexRestAdapter") as MockAdapter:
            instance = MockAdapter.return_value
            instance.open = AsyncMock()
            instance.close = AsyncMock()
            instance.delete_bom_component = AsyncMock(
                return_value={"success": True, "data": {"MSID": "000"}}
            )

            result = await _dispatch_mi_call(
                "PDS002MI.Delete",
                {
                    "parent_item": "LF100001", "component_item": "LF200010",
                    "operation_number": 10, "from_date": 20240101,
                    "facility": "L",
                },
                "PDS002MI.Delete:ecn-1:bc-1:close",
            )

        instance.delete_bom_component.assert_awaited_once()
        assert result == {"success": True, "data": {"MSID": "000"}}

    @pytest.mark.asyncio
    async def test_unknown_transaction_still_raises(self):
        """Regression guard — an unrecognised mi_transaction string (e.g. a
        stale PDS002MI.UpdateComponent row queued before I2-19) must fail
        loudly, not silently resolve to some other handler."""
        with patch("src.adapters.erp.movex.MovexRestAdapter") as MockAdapter:
            instance = MockAdapter.return_value
            instance.open = AsyncMock()
            instance.close = AsyncMock()

            with pytest.raises(ValueError, match="Unknown MI transaction"):
                await _dispatch_mi_call("PDS002MI.NotARealTransaction", {}, "ikey")

    @pytest.mark.asyncio
    async def test_update_component_is_no_longer_dispatchable(self):
        """I2-19 — PDS002MI.UpdateComponent must not be on the dispatch
        table at all (it was retired, not just guarded), since TDAT is
        confirmed broken on movex-rest-api."""
        with patch("src.adapters.erp.movex.MovexRestAdapter") as MockAdapter:
            instance = MockAdapter.return_value
            instance.open = AsyncMock()
            instance.close = AsyncMock()
            instance.update_bom_component = AsyncMock(return_value={"data": {"MSID": ""}})

            with pytest.raises(ValueError, match="Unknown MI transaction"):
                await _dispatch_mi_call(
                    "PDS002MI.UpdateComponent",
                    {
                        "parent_item": "LF100001", "component_item": "LF200010",
                        "operation_number": 10, "from_date": 20240101, "to_date": 20260831,
                        "facility": "L",
                    },
                    "PDS002MI.UpdateComponent:ecn-1:bc-1:close",
                )

        instance.update_bom_component.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_other_transactions_unaffected(self):
        """Regression guard — AddComponent dispatch must be unaffected by
        the UpdateComponent retirement."""
        with patch("src.adapters.erp.movex.MovexRestAdapter") as MockAdapter:
            instance = MockAdapter.return_value
            instance.open = AsyncMock()
            instance.close = AsyncMock()
            instance.add_bom_component = AsyncMock(return_value={"success": True, "data": {"MSID": "000"}})

            result = await _dispatch_mi_call(
                "PDS002MI.AddComponent",
                {
                    "parent_item": "LF100001", "component_item": "LF200010",
                    "quantity": 4.0, "unit_of_measure": "EA",
                    "operation_number": 10, "from_date": 20260901,
                    "facility": "L",
                },
                "PDS002MI.AddComponent:ecn-1:bc-1",
            )

        instance.add_bom_component.assert_awaited_once()
        assert result == {"success": True, "data": {"MSID": "000"}}
