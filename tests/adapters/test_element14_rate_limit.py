"""element14 rate-limit and daily-budget guard tests.

The key issued for the "Oskar" app carries documented limits (2026-08-28):
  * 2 calls per second
  * 1,000 calls per day

Unlike DigiKey, element14 returns NO quota headers, so neither limit can be
read back from a response — the adapter has to track both locally. That makes
these guards load-bearing rather than advisory: nothing else will stop a burst
from breaching the per-second cap or a runaway loop from burning the day's
budget.

Two different mechanisms, deliberately:
  * per-second  -> THROTTLE (sleep). Breaching it is a transient, self-
                   correcting condition; waiting a few hundred ms is the
                   correct response and is invisible to the caller.
  * per-day     -> REFUSE (raise). Sleeping until midnight is never the right
                   answer; the caller needs to know the budget is gone.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.adapters.suppliers.element14 import (
    Element14Adapter,
    Element14DailyBudgetExhausted,
)


def _adapter(monkeypatch, *, per_second=2, daily=1000):
    monkeypatch.setenv("ELEMENT14_API_KEY", "test-key")
    monkeypatch.setenv("ELEMENT14_MAX_CALLS_PER_SECOND", str(per_second))
    monkeypatch.setenv("ELEMENT14_DAILY_CALL_BUDGET", str(daily))
    return Element14Adapter()


def _ok_response():
    return {"keywordSearchReturn": {"products": []}}


class TestConfiguration:
    def test_reads_documented_defaults(self, monkeypatch):
        """Defaults match the key's real documented limits, so an unset env
        does not silently give the adapter more headroom than it has."""
        monkeypatch.setenv("ELEMENT14_API_KEY", "k")
        monkeypatch.delenv("ELEMENT14_MAX_CALLS_PER_SECOND", raising=False)
        monkeypatch.delenv("ELEMENT14_DAILY_CALL_BUDGET", raising=False)
        adapter = Element14Adapter()
        assert adapter._max_calls_per_second == 2
        assert adapter._daily_budget == 1000

    def test_limits_are_overridable(self, monkeypatch):
        adapter = _adapter(monkeypatch, per_second=5, daily=500)
        assert adapter._max_calls_per_second == 5
        assert adapter._daily_budget == 500


class TestPerSecondThrottle:
    @pytest.mark.asyncio
    async def test_calls_within_limit_do_not_sleep(self, monkeypatch):
        adapter = _adapter(monkeypatch, per_second=2)
        with (
            patch.object(adapter, "_raw_get", new_callable=AsyncMock) as raw,
            patch("src.adapters.suppliers.element14.asyncio.sleep", new_callable=AsyncMock) as sleep,
        ):
            raw.return_value = _ok_response()
            await adapter._get({"term": "any:x"})
            await adapter._get({"term": "any:y"})

        sleep.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_third_call_in_same_second_sleeps(self, monkeypatch):
        """2 calls/sec means the 3rd must wait — this is the actual limit."""
        adapter = _adapter(monkeypatch, per_second=2)
        with (
            patch.object(adapter, "_raw_get", new_callable=AsyncMock) as raw,
            patch("src.adapters.suppliers.element14.asyncio.sleep", new_callable=AsyncMock) as sleep,
        ):
            raw.return_value = _ok_response()
            await adapter._get({"term": "1"})
            await adapter._get({"term": "2"})
            await adapter._get({"term": "3"})

        sleep.assert_awaited()
        assert sleep.await_args.args[0] > 0

    @pytest.mark.asyncio
    async def test_throttle_is_transparent_to_the_caller(self, monkeypatch):
        """Throttling must not change the result — it only delays it."""
        adapter = _adapter(monkeypatch, per_second=1)
        with (
            patch.object(adapter, "_raw_get", new_callable=AsyncMock) as raw,
            patch("src.adapters.suppliers.element14.asyncio.sleep", new_callable=AsyncMock),
        ):
            raw.return_value = _ok_response()
            await adapter._get({"term": "1"})
            result = await adapter._get({"term": "2"})

        assert result == _ok_response()

    @pytest.mark.asyncio
    async def test_old_calls_fall_out_of_the_window(self, monkeypatch):
        """The window is a sliding 1s, not a fixed bucket — a call from 5s ago
        must not count against the current second."""
        adapter = _adapter(monkeypatch, per_second=2)
        adapter._call_times.extend([0.0, 0.5])  # ancient, relative to now
        with (
            patch.object(adapter, "_raw_get", new_callable=AsyncMock) as raw,
            patch("src.adapters.suppliers.element14.asyncio.sleep", new_callable=AsyncMock) as sleep,
        ):
            raw.return_value = _ok_response()
            await adapter._get({"term": "1"})

        sleep.assert_not_awaited()


class TestDailyBudget:
    @pytest.mark.asyncio
    async def test_calls_are_counted(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_raw_get", new_callable=AsyncMock) as raw:
            raw.return_value = _ok_response()
            await adapter._get({"term": "1"})
            await adapter._get({"term": "2"})

        assert adapter._calls_today == 2

    @pytest.mark.asyncio
    async def test_exhausted_budget_refuses_rather_than_sleeping(self, monkeypatch):
        """Sleeping until midnight is never the right answer — the caller
        needs to know the budget is gone."""
        adapter = _adapter(monkeypatch, daily=2)
        with patch.object(adapter, "_raw_get", new_callable=AsyncMock) as raw:
            raw.return_value = _ok_response()
            await adapter._get({"term": "1"})
            await adapter._get({"term": "2"})
            with pytest.raises(Element14DailyBudgetExhausted):
                await adapter._get({"term": "3"})

    @pytest.mark.asyncio
    async def test_refusal_does_not_consume_a_call(self, monkeypatch):
        adapter = _adapter(monkeypatch, daily=1)
        with patch.object(adapter, "_raw_get", new_callable=AsyncMock) as raw:
            raw.return_value = _ok_response()
            await adapter._get({"term": "1"})
            with pytest.raises(Element14DailyBudgetExhausted):
                await adapter._get({"term": "2"})

        assert raw.await_count == 1

    @pytest.mark.asyncio
    async def test_counter_resets_on_a_new_day(self, monkeypatch):
        adapter = _adapter(monkeypatch, daily=1)
        with patch.object(adapter, "_raw_get", new_callable=AsyncMock) as raw:
            raw.return_value = _ok_response()
            await adapter._get({"term": "1"})
            # Simulate the day rolling over
            adapter._budget_day = "2000-01-01"
            await adapter._get({"term": "2"})

        assert adapter._calls_today == 1

    @pytest.mark.asyncio
    async def test_budget_exhaustion_degrades_the_chain_not_the_request(self, monkeypatch):
        """SupplierChain catches adapter exceptions and falls through, so an
        exhausted budget must surface as an adapter exception — NOT as an
        empty dict, which the chain would cache as 'no such part'."""
        adapter = _adapter(monkeypatch, daily=0)
        with pytest.raises(Element14DailyBudgetExhausted):
            await adapter.get_part("RC0402FR-0710KL")


class TestSearchCostAwareness:
    @pytest.mark.asyncio
    async def test_search_limit_is_capped_to_protect_the_budget(self, monkeypatch):
        """One search is one API call regardless of numberOfResults, but an
        unbounded limit invites huge responses. Capped at element14's own
        documented per-call maximum."""
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_raw_get", new_callable=AsyncMock) as raw:
            raw.return_value = _ok_response()
            await adapter.search("resistor", limit=5000)

        params = raw.await_args.args[0]
        assert params["resultsSettings.numberOfResults"] <= 50
