"""
Unit tests for src/adapters/suppliers/chain.py

Covers:
  - Cache hit: returns cached result without calling any adapter
  - Cache miss + first adapter succeeds: writes to cache, returns result
  - Cache miss + first adapter fails, second succeeds: skips failed adapter
  - Cache miss + all adapters fail: returns {}
  - Cache miss + all adapters return empty: returns {}
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.suppliers.chain import SupplierChain


def _make_session(cached_row=None):
    """Build a mock AsyncSession that returns cached_row from _cache_get queries."""
    mock_result = MagicMock()
    mock_result.first.return_value = cached_row
    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)
    return session


def _adapter(supplier_id: str, result: dict | Exception):
    """Build a mock SupplierAdapter."""
    a = AsyncMock()
    a.supplier_id = supplier_id
    if isinstance(result, Exception):
        a.get_part = AsyncMock(side_effect=result)
    else:
        a.get_part = AsyncMock(return_value=result)
    return a


@pytest.mark.asyncio
async def test_cache_hit_returns_cached_without_adapter_call():
    # Row shape follows _cache_get's SELECT: the last two columns are the
    # commercial half added by migration 0033 (NULL here — descriptive-only
    # row, which is what a pre-0033 row looks like after the scrub).
    cached_row = ("10kΩ resistor", "Yageo", "Passive", "Active", "digikey", None, None, None)
    session = _make_session(cached_row)
    adapter = _adapter("digikey", {"description": "Should not be called"})

    chain = SupplierChain(session, [adapter])
    result = await chain.get_part("RC0402FR-0710KL")

    assert result["description"] == "10kΩ resistor"
    adapter.get_part.assert_not_called()


@pytest.mark.asyncio
async def test_cache_hit_with_raw_json_populated():
    """Regression test: raw_json is a jsonb column — asyncpg/SQLAlchemy return
    it already deserialized as a dict, not a JSON string. A prior bug called
    json.loads() on it unconditionally, raising TypeError on any real cache
    hit with data in raw_json (only ever masked because the other cache-hit
    test above used raw_json=None, which skips the json.loads() call
    entirely).

    raw_json carries DESCRIPTIVE fields only since migration 0033 — unit_price
    used to appear here and is now scrubbed out into commercial_json, so this
    fixture no longer includes it. Commercial caching is covered in
    tests/adapters/test_supplier_cache_ttl.py."""
    raw_json_dict = {"mounting_type": "TH", "digikey_part_number": "DK-123-ND"}
    cached_row = ("10kΩ resistor", "Yageo", "Passive", "Active", "digikey", raw_json_dict, None, None)
    session = _make_session(cached_row)
    adapter = _adapter("digikey", {"description": "Should not be called"})

    chain = SupplierChain(session, [adapter])
    result = await chain.get_part("RC0402FR-0710KL")

    assert result["description"] == "10kΩ resistor"
    assert result["mounting_type"] == "TH"
    assert result["digikey_part_number"] == "DK-123-ND"
    adapter.get_part.assert_not_called()


@pytest.mark.asyncio
async def test_cache_miss_first_adapter_returns_result():
    session = _make_session(cached_row=None)
    adapter = _adapter("digikey", {"description": "10kΩ 1% resistor", "manufacturer": "Yageo"})

    chain = SupplierChain(session, [adapter])
    result = await chain.get_part("RC0402FR-0710KL")

    assert result["description"] == "10kΩ 1% resistor"
    adapter.get_part.assert_awaited_once_with("RC0402FR-0710KL")
    # cache_set should have been called
    assert session.execute.call_count == 2  # cache_get + cache_set


@pytest.mark.asyncio
async def test_cache_miss_first_adapter_fails_second_succeeds():
    session = _make_session(cached_row=None)
    a1 = _adapter("digikey", Exception("API down"))
    a2 = _adapter("nexar", {"description": "Capacitor 100nF", "manufacturer": "Murata"})

    chain = SupplierChain(session, [a1, a2])
    result = await chain.get_part("GRM21BR61A106KE18L")

    assert result["description"] == "Capacitor 100nF"
    a1.get_part.assert_awaited_once()
    a2.get_part.assert_awaited_once()


@pytest.mark.asyncio
async def test_all_adapters_fail_returns_empty():
    session = _make_session(cached_row=None)
    a1 = _adapter("digikey", Exception("timeout"))
    a2 = _adapter("nexar", Exception("rate limited"))

    chain = SupplierChain(session, [a1, a2])
    result = await chain.get_part("UNKNOWN-MPN")

    assert result == {}


@pytest.mark.asyncio
async def test_all_adapters_return_empty_dict_returns_empty():
    session = _make_session(cached_row=None)
    a1 = _adapter("digikey", {})
    a2 = _adapter("nexar", {})

    chain = SupplierChain(session, [a1, a2])
    result = await chain.get_part("UNKNOWN-MPN")

    assert result == {}


@pytest.mark.asyncio
async def test_no_adapters_returns_empty():
    session = _make_session(cached_row=None)
    chain = SupplierChain(session, [])
    result = await chain.get_part("ANYTHING")
    assert result == {}
