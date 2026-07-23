"""FakeERPAdapter — full-ABC ERPAdapter test double backed by tests/fixtures/bom/*.json.

Distinct from tests/routers/*'s patch.object(MovexRestAdapter, ..., new_callable=AsyncMock)
pattern: that pattern patches one method at a time for router-level tests. Service-layer
BOM tests (Slice A/B) need a fully working adapter that returns realistic, internally
consistent fixture data across multiple calls — that's what FakeERPAdapter is for.
"""

import pytest

from tests.helpers.fake_erp import FakeERPAdapter


class TestFakeERPAdapterGetBom:
    async def test_returns_single_level_fixture_for_known_item(self):
        adapter = FakeERPAdapter()

        result = await adapter.get_bom("LF100001", "D")

        assert result["data"]["head"]["PRNO"] == "LF100001"
        assert len(result["data"]["records"]) == 12

    async def test_unknown_item_raises_lookup_error(self):
        adapter = FakeERPAdapter()

        with pytest.raises(LookupError):
            await adapter.get_bom("NOPE99999", "D")


class TestFakeERPAdapterCannedDefaults:
    async def test_health_check_returns_true(self):
        adapter = FakeERPAdapter()

        assert await adapter.health_check() is True
