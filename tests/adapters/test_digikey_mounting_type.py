"""
Unit tests for src/adapters/suppliers/digikey.py — mounting_type extraction (S9-3)

Covers:
  - _normalise_mounting_type: free-text DigiKey ValueText -> TH/SMD/MECHANICAL/OTHER
  - _extract_mounting_type: scans Product.Parameters for a mounting-type-equivalent attribute
  - DigiKeyAdapter.get_part: mounting_type key present in the normalised result
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import pybreaker

from src.adapters.suppliers.digikey import (
    DigiKeyAdapter,
    _call_with_breaker,
    _extract_mounting_type,
    _normalise_mounting_type,
)


# ── _normalise_mounting_type ────────────────────────────────────────────────────

class TestNormaliseMountingType:
    @pytest.mark.parametrize("raw,expected", [
        ("Surface Mount", "SMD"),
        ("Surface Mount, MOSFET", "SMD"),
        ("SMD", "SMD"),
        ("SMT", "SMD"),
        ("Through Hole", "TH"),
        ("Thru-Hole", "TH"),
        ("THT", "TH"),
        ("Mechanical", "MECHANICAL"),
        ("Hardware", "MECHANICAL"),
        ("Connector Housing", "MECHANICAL"),
        ("Chassis Mount", "OTHER"),
        ("Panel Mount", "OTHER"),
    ])
    def test_known_mappings(self, raw: str, expected: str) -> None:
        assert _normalise_mounting_type(raw) == expected

    def test_empty_string_returns_none(self) -> None:
        assert _normalise_mounting_type("") is None
        assert _normalise_mounting_type("   ") is None

    def test_case_insensitive(self) -> None:
        assert _normalise_mounting_type("SURFACE MOUNT") == "SMD"
        assert _normalise_mounting_type("through hole") == "TH"


# ── _extract_mounting_type ──────────────────────────────────────────────────────

class TestExtractMountingType:
    def test_finds_mounting_type_parameter(self) -> None:
        product = {
            "Parameters": [
                {"ParameterText": "Resistance", "ValueText": "10 kOhms"},
                {"ParameterText": "Mounting Type", "ValueText": "Surface Mount"},
            ]
        }
        assert _extract_mounting_type(product) == "SMD"

    def test_falls_back_to_package_case_parameter(self) -> None:
        product = {
            "Parameters": [
                {"ParameterText": "Package / Case", "ValueText": "Through Hole"},
            ]
        }
        assert _extract_mounting_type(product) == "TH"

    def test_no_parameters_returns_none(self) -> None:
        assert _extract_mounting_type({}) is None
        assert _extract_mounting_type({"Parameters": []}) is None

    def test_no_matching_parameter_returns_none(self) -> None:
        product = {"Parameters": [{"ParameterText": "Voltage", "ValueText": "5V"}]}
        assert _extract_mounting_type(product) is None

    def test_unrecognised_value_text_returns_other(self) -> None:
        product = {
            "Parameters": [{"ParameterText": "Mounting Type", "ValueText": "Chassis Mount"}]
        }
        assert _extract_mounting_type(product) == "OTHER"


# ── DigiKeyAdapter.get_part — mounting_type wiring ──────────────────────────────

class TestGetPartMountingType:
    @pytest.mark.asyncio
    async def test_get_part_includes_mounting_type(self, monkeypatch) -> None:
        monkeypatch.setenv("DIGIKEY_CLIENT_ID", "test-id")
        monkeypatch.setenv("DIGIKEY_CLIENT_SECRET", "test-secret")

        adapter = DigiKeyAdapter()
        adapter._access_token = "fake-token"
        import time
        adapter._token_expiry = time.monotonic() + 3600

        mock_response = MagicMock()
        mock_response.headers = {}
        mock_response.json.return_value = {
            "Product": {
                "Description": {"DetailedDescription": "10k resistor"},
                "Manufacturer": {"Name": "Yageo"},
                "Category": {"Name": "Resistors"},
                "ProductStatus": {"Status": "Active"},
                "ProductVariations": [{"DigiKeyProductNumber": "DK-123-ND"}],
                "UnitPrice": 0.01,
                "QuantityAvailable": 10000,
                "Parameters": [
                    {"ParameterText": "Mounting Type", "ValueText": "Surface Mount"},
                ],
            }
        }
        mock_response.raise_for_status = MagicMock()

        adapter._http = AsyncMock()
        adapter._http.get = AsyncMock(return_value=mock_response)

        result = await adapter.get_part("RC0402FR-0710KL")

        assert result["mounting_type"] == "SMD"
        assert result["description"] == "10k resistor"
        assert result["digikey_part_number"] == "DK-123-ND"

    @pytest.mark.asyncio
    async def test_get_part_mounting_type_none_when_absent(self, monkeypatch) -> None:
        monkeypatch.setenv("DIGIKEY_CLIENT_ID", "test-id")
        monkeypatch.setenv("DIGIKEY_CLIENT_SECRET", "test-secret")

        adapter = DigiKeyAdapter()
        adapter._access_token = "fake-token"
        import time
        adapter._token_expiry = time.monotonic() + 3600

        mock_response = MagicMock()
        mock_response.headers = {}
        mock_response.json.return_value = {
            "Product": {
                "Description": {"DetailedDescription": "Some part"},
                "Manufacturer": {"Name": "Acme"},
                "Category": {"Name": "Misc"},
                "ProductStatus": {"Status": "Active"},
                "ProductVariations": [{"DigiKeyProductNumber": "DK-999-ND"}],
                "Parameters": [],
            }
        }
        mock_response.raise_for_status = MagicMock()

        adapter._http = AsyncMock()
        adapter._http.get = AsyncMock(return_value=mock_response)

        result = await adapter.get_part("SOME-MPN")

        assert result["mounting_type"] is None


# ── _call_with_breaker — circuit breaker state machine (bug fix regression) ────

class TestCallWithBreaker:
    @pytest.mark.asyncio
    async def test_success_passes_through_result(self) -> None:
        cb = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=60)

        async def ok() -> str:
            return "value"

        result = await _call_with_breaker(cb, ok)
        assert result == "value"
        assert cb.current_state == "closed"

    @pytest.mark.asyncio
    async def test_failure_propagates_and_increments_fail_counter(self) -> None:
        cb = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=60)

        async def boom() -> None:
            raise ValueError("simulated failure")

        with pytest.raises(ValueError):
            await _call_with_breaker(cb, boom)
        assert cb.fail_counter == 1

    @pytest.mark.asyncio
    async def test_opens_after_fail_max_consecutive_failures(self) -> None:
        cb = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=60)

        async def boom() -> None:
            raise ValueError("simulated failure")

        # First fail_max - 1 failures raise the original exception.
        for _ in range(2):
            with pytest.raises(ValueError):
                await _call_with_breaker(cb, boom)

        # The failure that crosses the threshold trips the breaker open and
        # pybreaker raises CircuitBreakerError instead of the original exception
        # (see CircuitClosedState.on_failure — this is documented pybreaker behavior).
        with pytest.raises(pybreaker.CircuitBreakerError):
            await _call_with_breaker(cb, boom)

        assert cb.current_state == "open"

    @pytest.mark.asyncio
    async def test_open_circuit_rejects_without_calling_func(self) -> None:
        cb = pybreaker.CircuitBreaker(fail_max=1, reset_timeout=60)
        call_count = 0

        async def boom() -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError("simulated failure")

        # fail_max=1 — the single failure both trips the threshold AND opens
        # the breaker in the same call, so CircuitBreakerError is raised immediately.
        with pytest.raises(pybreaker.CircuitBreakerError):
            await _call_with_breaker(cb, boom)
        assert call_count == 1
        assert cb.current_state == "open"

        # Second call — circuit is open, breaker should short-circuit before calling boom again
        with pytest.raises(pybreaker.CircuitBreakerError):
            await _call_with_breaker(cb, boom)
        assert call_count == 1  # boom was NOT called again
