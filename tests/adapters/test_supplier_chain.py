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
    cached_row = ("10kΩ resistor", "Yageo", "Passive", "Active", "digikey", None)
    session = _make_session(cached_row)
    adapter = _adapter("digikey", {"description": "Should not be called"})

    chain = SupplierChain(session, [adapter])
    result = await chain.get_part("RC0402FR-0710KL")

    assert result["description"] == "10kΩ resistor"
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
