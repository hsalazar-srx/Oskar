"""
OSKAR — Scanfil APAC part number suggestion tests (S3-2)

GET /api/v1/parts/suggest-pn
  ?procurement_group=PAS&product_group=RES&cuno=AA[&commodity_override=12]

Auto-generates the next available Scanfil APAC part number on the no_match path.
Format: LF + {2-char CUNO} + {2-digit commodity} + {4-digit zero-padded seq}
Example: LFAA120023  (customer=AA, commodity=12=RES SMD, seq=23)

'LF' is the company prefix (legacy Startronics/SRXGlobal identifier). It does NOT
encode lead-free status — that is a separate MITMAS field (BBB/PBF).

Key design facts from Nick's template (ecn_item_upload_v13, 2026-04-29):
  - Both procurement_group AND product_group are required to resolve the commodity code.
  - Multiple commodity codes can map to the same (prgp, itcl) pair.
    e.g. PAS/RES → [11 TH, 12 SMD, 13 ResNet, 14 Varistor]
    In this case commodity_override is required; endpoint returns 422 with options if absent.
  - Some codes are shared across different (prgp, itcl) pairs with the same numeric range.
    e.g. ACT/LED=26 and EM/DISP=26 — they share the sequence namespace (by design).
  - Sequence = next available 4-digit slot from MVXCDTA.MITMAS for the 6-char prefix.
  - CUNO is 2 chars, uppercased (Movex customer code from OCUSMA).
  - CSP/CSP is a customer-supplied part — PN format is LFXXXXNNNN; not auto-sequenced.
  - TEM/TEMP has 4 commodity codes: 66, 76, 81, 90 (electrical, software, misc ranges).
  - PLA/INJEC and PLA/PLAMC each have 2 codes: 65 (standard) and 67 (off-the-shelf/cable tie).

TDD: written before implementation.

Run with: pytest tests/routers/test_pn_generation.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pybreaker
import pytest
from fastapi.testclient import TestClient

from src.adapters.erp.movex import MovexRestAdapter
from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app

_ENGINEER = CurrentUser(
    username="eng_user",
    display_name="Test Engineer",
    email="eng@scanfil.com",
    groups=["OSKAR-Engineers"],
    jti="test-jti-pn-001",
)

app.state.erp_adapter = MovexRestAdapter.__new__(MovexRestAdapter)


def _make_client(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ── Unique-code pairs (no override needed) ────────────────────────────────────

class TestSuggestPNUniqueCodes:
    """These (prgp, itcl) pairs map to exactly one commodity code."""

    def _get(self, prgp: str, itcl: str, seq: int = 1) -> dict:
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock) as mock:
            mock.return_value = seq
            client = _make_client(_ENGINEER)
            resp = client.get(
                "/api/v1/parts/suggest-pn",
                params={"procurement_group": prgp, "product_group": itcl, "cuno": "LM"},
            )
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_pcba_commodity_05(self):
        assert self._get("PCA", "PCBA")["commodity_code"] == "05"

    def test_pcb_rigid_commodity_10(self):
        assert self._get("PCB", "RIGID")["commodity_code"] == "10"

    def test_pcb_flexi_commodity_10(self):
        assert self._get("PCB", "FLEXI")["commodity_code"] == "10"

    def test_xtal_commodity_27(self):
        assert self._get("PAS", "XTAL")["commodity_code"] == "27"

    def test_led_commodity_26(self):
        assert self._get("ACT", "LED")["commodity_code"] == "26"

    def test_disp_commodity_26(self):
        assert self._get("EM", "DISP")["commodity_code"] == "26"

    def test_relay_commodity_52(self):
        assert self._get("MAG", "RELAY")["commodity_code"] == "52"

    def test_trfmr_commodity_53(self):
        assert self._get("EM", "TRFMR")["commodity_code"] == "53"

    def test_batt_commodity_58(self):
        assert self._get("EM", "BATT")["commodity_code"] == "58"

    def test_psu_commodity_59(self):
        assert self._get("EM", "PSU")["commodity_code"] == "59"

    def test_wires_commodity_61(self):
        assert self._get("HWR", "WIRES")["commodity_code"] == "61"

    def test_cbasy_commodity_62(self):
        assert self._get("EM", "CBASY")["commodity_code"] == "62"

    def test_hardw_commodity_69(self):
        assert self._get("HWR", "HARDW")["commodity_code"] == "69"


# ── Multi-code pairs: override required ───────────────────────────────────────

class TestSuggestPNMultiCode:
    """These (prgp, itcl) pairs have multiple commodity codes — override required."""

    def test_res_without_override_returns_422_with_options(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock):
            client = _make_client(_ENGINEER)
            resp = client.get(
                "/api/v1/parts/suggest-pn",
                params={"procurement_group": "PAS", "product_group": "RES", "cuno": "AA"},
            )
        assert resp.status_code == 422
        body = resp.json()
        assert "commodity_options" in body["detail"]
        options = body["detail"]["commodity_options"]
        assert set(options) == {"11", "12", "13", "14"}

    def test_res_with_override_12_returns_200(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock) as mock:
            mock.return_value = 1
            client = _make_client(_ENGINEER)
            resp = client.get(
                "/api/v1/parts/suggest-pn",
                params={"procurement_group": "PAS", "product_group": "RES",
                        "cuno": "AA", "commodity_override": "12"},
            )
        assert resp.status_code == 200
        assert resp.json()["commodity_code"] == "12"
        assert resp.json()["suggested_pn"] == "LFAA120001"

    def test_res_with_override_11_returns_200(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock) as mock:
            mock.return_value = 7
            client = _make_client(_ENGINEER)
            resp = client.get(
                "/api/v1/parts/suggest-pn",
                params={"procurement_group": "PAS", "product_group": "RES",
                        "cuno": "LM", "commodity_override": "11"},
            )
        assert resp.json()["suggested_pn"] == "LFLM110007"

    def test_caps_without_override_returns_422(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock):
            client = _make_client(_ENGINEER)
            resp = client.get(
                "/api/v1/parts/suggest-pn",
                params={"procurement_group": "PAS", "product_group": "CAPS", "cuno": "AA"},
            )
        assert resp.status_code == 422
        options = resp.json()["detail"]["commodity_options"]
        assert set(options) == {"20", "21", "22"}

    def test_diode_without_override_returns_422(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock):
            client = _make_client(_ENGINEER)
            resp = client.get(
                "/api/v1/parts/suggest-pn",
                params={"procurement_group": "ACT", "product_group": "DIODE", "cuno": "AA"},
            )
        assert resp.status_code == 422
        options = resp.json()["detail"]["commodity_options"]
        assert set(options) == {"24", "25"}

    def test_xstor_without_override_returns_422(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock):
            client = _make_client(_ENGINEER)
            resp = client.get(
                "/api/v1/parts/suggest-pn",
                params={"procurement_group": "ACT", "product_group": "XSTOR", "cuno": "AA"},
            )
        assert resp.status_code == 422
        options = resp.json()["detail"]["commodity_options"]
        assert set(options) == {"30", "31", "32"}

    def test_connt_without_override_returns_422(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock):
            client = _make_client(_ENGINEER)
            resp = client.get(
                "/api/v1/parts/suggest-pn",
                params={"procurement_group": "EM", "product_group": "CONNT", "cuno": "AA"},
            )
        assert resp.status_code == 422
        options = resp.json()["detail"]["commodity_options"]
        assert set(options) == {"35", "36", "37", "38"}

    def test_ic_without_override_returns_422(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock):
            client = _make_client(_ENGINEER)
            resp = client.get(
                "/api/v1/parts/suggest-pn",
                params={"procurement_group": "ACT", "product_group": "IC", "cuno": "AA"},
            )
        assert resp.status_code == 422
        options = resp.json()["detail"]["commodity_options"]
        assert set(options) == {"40", "41", "49", "51"}

    def test_rfdvc_without_override_returns_422(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock):
            client = _make_client(_ENGINEER)
            resp = client.get(
                "/api/v1/parts/suggest-pn",
                params={"procurement_group": "EM", "product_group": "RFDVC", "cuno": "AA"},
            )
        assert resp.status_code == 422
        options = resp.json()["detail"]["commodity_options"]
        assert set(options) == {"56", "57"}

    def test_invalid_override_returns_422(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock):
            client = _make_client(_ENGINEER)
            resp = client.get(
                "/api/v1/parts/suggest-pn",
                params={"procurement_group": "PAS", "product_group": "RES",
                        "cuno": "AA", "commodity_override": "99"},
            )
        assert resp.status_code == 422

    def test_pla_injec_without_override_returns_422(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock):
            client = _make_client(_ENGINEER)
            resp = client.get(
                "/api/v1/parts/suggest-pn",
                params={"procurement_group": "PLA", "product_group": "INJEC", "cuno": "AA"},
            )
        assert resp.status_code == 422
        options = resp.json()["detail"]["commodity_options"]
        assert set(options) == {"65", "67"}

    def test_pla_plamc_without_override_returns_422(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock):
            client = _make_client(_ENGINEER)
            resp = client.get(
                "/api/v1/parts/suggest-pn",
                params={"procurement_group": "PLA", "product_group": "PLAMC", "cuno": "AA"},
            )
        assert resp.status_code == 422
        options = resp.json()["detail"]["commodity_options"]
        assert set(options) == {"65", "67"}

    def test_tem_temp_without_override_returns_422(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock):
            client = _make_client(_ENGINEER)
            resp = client.get(
                "/api/v1/parts/suggest-pn",
                params={"procurement_group": "TEM", "product_group": "TEMP", "cuno": "AA"},
            )
        assert resp.status_code == 422
        options = resp.json()["detail"]["commodity_options"]
        assert set(options) == {"66", "76", "81", "90"}

    def test_tem_temp_with_override_81_returns_200(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock) as mock:
            mock.return_value = 3
            client = _make_client(_ENGINEER)
            resp = client.get(
                "/api/v1/parts/suggest-pn",
                params={"procurement_group": "TEM", "product_group": "TEMP",
                        "cuno": "LM", "commodity_override": "81"},
            )
        assert resp.status_code == 200
        assert resp.json()["suggested_pn"] == "LFLM810003"

    def test_indtr_without_override_returns_422(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock):
            client = _make_client(_ENGINEER)
            resp = client.get(
                "/api/v1/parts/suggest-pn",
                params={"procurement_group": "MAG", "product_group": "INDTR", "cuno": "AA"},
            )
        assert resp.status_code == 422
        options = resp.json()["detail"]["commodity_options"]
        assert set(options) == {"54", "55", "56"}

    def test_swtch_without_override_returns_422(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock):
            client = _make_client(_ENGINEER)
            resp = client.get(
                "/api/v1/parts/suggest-pn",
                params={"procurement_group": "EM", "product_group": "SWTCH", "cuno": "AA"},
            )
        assert resp.status_code == 422
        options = resp.json()["detail"]["commodity_options"]
        assert set(options) == {"44", "45"}


# ── PN format correctness ─────────────────────────────────────────────────────

class TestSuggestPNFormat:

    def _get_pn(self, prgp: str, itcl: str, cuno: str, seq: int, override: str | None = None) -> str:
        params = {"procurement_group": prgp, "product_group": itcl, "cuno": cuno}
        if override:
            params["commodity_override"] = override
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock) as mock:
            mock.return_value = seq
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/parts/suggest-pn", params=params)
        assert resp.status_code == 200, resp.text
        return resp.json()["suggested_pn"]

    def test_pn_always_10_chars(self):
        pn = self._get_pn("PCA", "PCBA", "LM", 1)
        assert len(pn) == 10

    def test_pn_starts_with_lf(self):
        pn = self._get_pn("PCA", "PCBA", "LM", 1)
        assert pn.startswith("LF")

    def test_cuno_lowercased_input_uppercased_in_pn(self):
        pn = self._get_pn("PCA", "PCBA", "lm", 1)
        assert pn[2:4] == "LM"

    def test_sequence_1_pads_to_0001(self):
        pn = self._get_pn("PCA", "PCBA", "LM", 1)
        assert pn[6:] == "0001"

    def test_sequence_99_pads_to_0099(self):
        pn = self._get_pn("PCA", "PCBA", "LM", 99)
        assert pn[6:] == "0099"

    def test_sequence_1000_is_4_digits(self):
        pn = self._get_pn("PCA", "PCBA", "LM", 1000)
        assert pn[6:] == "1000"

    def test_commodity_in_correct_position(self):
        pn = self._get_pn("PCA", "PCBA", "LM", 1)
        assert pn[4:6] == "05"

    def test_prefix_passed_to_adapter(self):
        params = {"procurement_group": "PCA", "product_group": "PCBA", "cuno": "LM"}
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock) as mock:
            mock.return_value = 1
            client = _make_client(_ENGINEER)
            client.get("/api/v1/parts/suggest-pn", params=params)
        assert mock.call_args.kwargs["prefix"] == "LFLM05"

    def test_only_prefix_passed_to_adapter(self):
        # CONO is injected by the adapter internally — router must NOT pass it
        params = {"procurement_group": "PCA", "product_group": "PCBA", "cuno": "LM"}
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock) as mock:
            mock.return_value = 1
            client = _make_client(_ENGINEER)
            client.get("/api/v1/parts/suggest-pn", params=params)
        assert "cono" not in mock.call_args.kwargs
        assert mock.call_args.kwargs["prefix"] == "LFLM05"

    def test_response_includes_procurement_group(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock) as mock:
            mock.return_value = 1
            client = _make_client(_ENGINEER)
            resp = client.get(
                "/api/v1/parts/suggest-pn",
                params={"procurement_group": "PCA", "product_group": "PCBA", "cuno": "LM"},
            )
        assert resp.json()["procurement_group"] == "PCA"

    def test_response_includes_product_group(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock) as mock:
            mock.return_value = 1
            client = _make_client(_ENGINEER)
            resp = client.get(
                "/api/v1/parts/suggest-pn",
                params={"procurement_group": "PCA", "product_group": "PCBA", "cuno": "LM"},
            )
        assert resp.json()["product_group"] == "PCBA"


# ── Input validation ──────────────────────────────────────────────────────────

class TestSuggestPNValidation:

    def test_missing_procurement_group_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.get("/api/v1/parts/suggest-pn",
                          params={"product_group": "PCBA", "cuno": "LM"})
        assert resp.status_code == 422

    def test_missing_product_group_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.get("/api/v1/parts/suggest-pn",
                          params={"procurement_group": "PCA", "cuno": "LM"})
        assert resp.status_code == 422

    def test_missing_cuno_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.get("/api/v1/parts/suggest-pn",
                          params={"procurement_group": "PCA", "product_group": "PCBA"})
        assert resp.status_code == 422

    def test_cuno_too_long_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.get("/api/v1/parts/suggest-pn",
                          params={"procurement_group": "PCA", "product_group": "PCBA", "cuno": "LMX"})
        assert resp.status_code == 422

    def test_unknown_product_group_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.get("/api/v1/parts/suggest-pn",
                          params={"procurement_group": "PCA", "product_group": "BOGUS", "cuno": "LM"})
        assert resp.status_code == 422

    def test_unknown_procurement_group_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.get("/api/v1/parts/suggest-pn",
                          params={"procurement_group": "BOGUS", "product_group": "PCBA", "cuno": "LM"})
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/parts/suggest-pn",
                          params={"procurement_group": "PCA", "product_group": "PCBA", "cuno": "LM"})
        assert resp.status_code == 401


# ── ERP error handling ────────────────────────────────────────────────────────

class TestSuggestPNERPErrors:

    def test_circuit_breaker_open_returns_503(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock) as mock:
            mock.side_effect = pybreaker.CircuitBreakerError()
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/parts/suggest-pn",
                              params={"procurement_group": "PCA", "product_group": "PCBA", "cuno": "LM"})
        assert resp.status_code == 503

    def test_erp_connect_error_returns_502(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock) as mock:
            mock.side_effect = httpx.ConnectError("refused")
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/parts/suggest-pn",
                              params={"procurement_group": "PCA", "product_group": "PCBA", "cuno": "LM"})
        assert resp.status_code == 502

    def test_erp_timeout_returns_502(self):
        with patch.object(MovexRestAdapter, "get_next_itno_sequence", new_callable=AsyncMock) as mock:
            mock.side_effect = httpx.TimeoutException("timeout")
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/parts/suggest-pn",
                              params={"procurement_group": "PCA", "product_group": "PCBA", "cuno": "LM"})
        assert resp.status_code == 502
