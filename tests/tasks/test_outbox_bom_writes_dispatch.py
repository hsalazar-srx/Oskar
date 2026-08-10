"""
OSKAR — movex_outbox dispatch wiring for PDS002MI.UpdateComponent (Slice E,
W-1).

_dispatch_mi_call's dispatch dict maps mi_transaction strings to
MovexRestAdapter write methods. PDS002MI.UpdateComponent (Slice E's
DELETE/CHANGE-close BOM writes) must resolve to update_bom_component so
_queue_bom_changes_outbox's close rows actually dispatch — mirrors the
existing PDS002MI.AddComponent -> add_bom_component /
PDS002MI.DeleteComponent -> delete_bom_component entries.

W-1 is confirmed not yet built on movex-rest-api — this test only proves
Oskar-side dispatch wiring is correct (mocked adapter), not a live call.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.tasks.movex_outbox import _dispatch_mi_call


class TestUpdateComponentDispatch:
    @pytest.mark.asyncio
    async def test_update_component_dispatches_to_update_bom_component(self):
        with patch("src.adapters.erp.movex.MovexRestAdapter") as MockAdapter:
            instance = MockAdapter.return_value
            instance.open = AsyncMock()
            instance.close = AsyncMock()
            instance.update_bom_component = AsyncMock(return_value={"data": {"MSID": ""}})

            result = await _dispatch_mi_call(
                "PDS002MI.UpdateComponent",
                {
                    "parent_item": "LF100001", "component_item": "LF200010",
                    "operation_number": 10, "from_date": 20240101, "to_date": 20260831,
                    "facility": "L",
                },
                "PDS002MI.UpdateComponent:ecn-1:bc-1:close",
            )

        instance.update_bom_component.assert_awaited_once_with(
            parent_item="LF100001", component_item="LF200010",
            operation_number=10, from_date=20240101, to_date=20260831,
            facility="L", idempotency_key="PDS002MI.UpdateComponent:ecn-1:bc-1:close",
        )
        assert result == {"data": {"MSID": ""}}

    @pytest.mark.asyncio
    async def test_unknown_transaction_still_raises(self):
        """Regression guard — adding UpdateComponent must not accidentally
        make the unknown-transaction ValueError path stop working."""
        with patch("src.adapters.erp.movex.MovexRestAdapter") as MockAdapter:
            instance = MockAdapter.return_value
            instance.open = AsyncMock()
            instance.close = AsyncMock()

            with pytest.raises(ValueError, match="Unknown MI transaction"):
                await _dispatch_mi_call("PDS002MI.NotARealTransaction", {}, "ikey")
