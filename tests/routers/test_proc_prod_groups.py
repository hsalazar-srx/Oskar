"""
OSKAR — Proc & Product Group auto-population tests (S3-4)

VSM p.6 pain: PE has to find, manually, the right commodity code based on MPN
description or checking the Data Sheet. This wastes ~30 min per new part.

Two endpoints eliminate the manual lookup:

GET  /api/v1/parts/groups
    Returns all valid (procurement_group, product_group) pairs with their
    commodity code(s) from the Engineering Team's matrix. Drives the dropdowns in the ECN
    item UI — engineer picks from a validated list instead of typing free-text.
    No auth required (reference data). Optional ?prgp= and ?itcl= filters.

POST /api/v1/parts/autofill-groups
    Writes procurement_group + product_group onto an ecn_items row.
    The engineer selects the pair from the dropdown; this endpoint persists the
    choice and returns the updated item. Validates the pair is in the matrix
    before writing (prevents bad data reaching Movex via S3-2 suggest-pn).
    Auth required — engineer role minimum.

No fuzzy-text-to-group inference (AI-gated; out of scope for Iteration 1).

TDD: written before implementation.
Run with: pytest tests/routers/test_proc_prod_groups.py -v
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app

_ENGINEER = CurrentUser(
    username="eng_user",
    display_name="Test Engineer",
    email="eng@scanfil.com",
    groups=["OSKAR-Engineers"],
    jti="test-jti-groups-001",
)

_ECN_ID = str(uuid.uuid4())
_ITEM_ID = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _client_with_auth() -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: _ENGINEER
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


def _client_no_auth() -> TestClient:
    app.dependency_overrides.clear()
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/parts/groups — dropdown data
# ─────────────────────────────────────────────────────────────────────────────

class TestGroupsList:

    def test_returns_200(self):
        r = _client_no_auth().get("/api/v1/parts/groups")
        assert r.status_code == 200

    def test_response_is_list(self):
        data = _client_no_auth().get("/api/v1/parts/groups").json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_each_entry_has_required_fields(self):
        for entry in _client_no_auth().get("/api/v1/parts/groups").json():
            assert "procurement_group" in entry
            assert "product_group" in entry
            assert "commodity_codes" in entry
            assert isinstance(entry["commodity_codes"], list)
            assert len(entry["commodity_codes"]) > 0

    def test_no_duplicate_pairs(self):
        entries = _client_no_auth().get("/api/v1/parts/groups").json()
        keys = [(e["procurement_group"], e["product_group"]) for e in entries]
        assert len(keys) == len(set(keys))

    # ── Known-pair spot checks from Engineering Team's matrix ─────────────────

    def test_pas_res_has_four_codes(self):
        """Resistors are the most common ECN item — 4 commodity codes."""
        entries = _client_no_auth().get("/api/v1/parts/groups").json()
        pas_res = [e for e in entries if e["procurement_group"] == "PAS" and e["product_group"] == "RES"]
        assert len(pas_res) == 1
        assert sorted(pas_res[0]["commodity_codes"]) == ["11", "12", "13", "14"]

    def test_pcb_rigid_single_code_10(self):
        entries = _client_no_auth().get("/api/v1/parts/groups").json()
        match = [e for e in entries if e["procurement_group"] == "PCB" and e["product_group"] == "RIGID"]
        assert len(match) == 1
        assert match[0]["commodity_codes"] == ["10"]

    def test_tem_temp_has_four_codes(self):
        """Template items span 66/76/81/90 — software, firmware, misc, electrical."""
        entries = _client_no_auth().get("/api/v1/parts/groups").json()
        match = [e for e in entries if e["procurement_group"] == "TEM" and e["product_group"] == "TEMP"]
        assert len(match) == 1
        assert sorted(match[0]["commodity_codes"]) == ["66", "76", "81", "90"]

    def test_pla_injec_has_two_codes(self):
        entries = _client_no_auth().get("/api/v1/parts/groups").json()
        match = [e for e in entries if e["procurement_group"] == "PLA" and e["product_group"] == "INJEC"]
        assert len(match) == 1
        assert sorted(match[0]["commodity_codes"]) == ["65", "67"]

    def test_csp_csp_code_xx(self):
        """Customer-supplied parts use code XX — must be in list for completeness."""
        entries = _client_no_auth().get("/api/v1/parts/groups").json()
        match = [e for e in entries if e["procurement_group"] == "CSP" and e["product_group"] == "CSP"]
        assert len(match) == 1
        assert match[0]["commodity_codes"] == ["XX"]

    def test_act_ic_has_four_codes(self):
        """ICs: TH=40, SMD=41, Opto=49, Sensor=51."""
        entries = _client_no_auth().get("/api/v1/parts/groups").json()
        match = [e for e in entries if e["procurement_group"] == "ACT" and e["product_group"] == "IC"]
        assert len(match) == 1
        assert sorted(match[0]["commodity_codes"]) == ["40", "41", "49", "51"]

    def test_em_connt_has_four_codes(self):
        """Connectors: TH=35, SMD=36, Other=37, Socket=38."""
        entries = _client_no_auth().get("/api/v1/parts/groups").json()
        match = [e for e in entries if e["procurement_group"] == "EM" and e["product_group"] == "CONNT"]
        assert len(match) == 1
        assert sorted(match[0]["commodity_codes"]) == ["35", "36", "37", "38"]

    # ── Optional filters ──────────────────────────────────────────────────────

    def test_filter_by_prgp(self):
        r = _client_no_auth().get("/api/v1/parts/groups?prgp=EM")
        assert r.status_code == 200
        for e in r.json():
            assert e["procurement_group"] == "EM"

    def test_filter_by_itcl(self):
        r = _client_no_auth().get("/api/v1/parts/groups?itcl=CAPS")
        assert r.status_code == 200
        for e in r.json():
            assert e["product_group"] == "CAPS"

    def test_filter_case_insensitive(self):
        lower = _client_no_auth().get("/api/v1/parts/groups?prgp=em").json()
        upper = _client_no_auth().get("/api/v1/parts/groups?prgp=EM").json()
        assert lower == upper

    def test_filter_both_prgp_and_itcl(self):
        r = _client_no_auth().get("/api/v1/parts/groups?prgp=ACT&itcl=IC")
        assert r.status_code == 200
        entries = r.json()
        assert len(entries) == 1
        assert entries[0]["procurement_group"] == "ACT"
        assert entries[0]["product_group"] == "IC"

    def test_unknown_prgp_returns_empty_not_404(self):
        r = _client_no_auth().get("/api/v1/parts/groups?prgp=ZZZ")
        assert r.status_code == 200
        assert r.json() == []

    def test_no_auth_required(self):
        """Reference data — must not require a JWT."""
        r = _client_no_auth().get("/api/v1/parts/groups")
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/parts/autofill-groups — write prgp + itcl onto ecn_items row
# ─────────────────────────────────────────────────────────────────────────────

def _mock_item(prgp: str | None = None, itcl: str | None = None) -> MagicMock:
    item = MagicMock()
    item.id = _ITEM_ID
    item.ecn_id = _ECN_ID
    item.line_number = 1
    item.is_new_item = True
    item.item_number = "LFAA120001"
    item.item_name = "RES 10K 1% 0402"
    item.description_2 = None
    item.drawing_number = None
    item.drawing_created = False
    item.procurement_group = prgp
    item.product_group = itcl
    item.unit_of_measure = "EA"
    item.item_group = None
    item.customer_alias = None
    item.effectivity_type = "IMMEDIATE"
    item.effectivity_from = None
    item.created_at = "2026-05-15T00:00:00"
    item.updated_at = "2026-05-15T00:00:00"
    item.mpns = []
    return item


class TestAutofillGroups:

    def _post(self, body: dict) -> "requests.Response":
        return _client_with_auth().post("/api/v1/parts/autofill-groups", json=body)

    # ── 200 happy-path ────────────────────────────────────────────────────────

    def test_valid_unique_code_pair_returns_200(self):
        """PAS/XTAL → single code 27 — no override needed."""
        updated = _mock_item(prgp="PAS", itcl="XTAL")
        with patch("src.routers.parts.ECNService") as MockSvc:
            svc = MockSvc.return_value
            svc.get_item = AsyncMock(return_value=_mock_item())
            svc.update_item = AsyncMock(return_value=updated)
            r = self._post({
                "ecn_id": _ECN_ID,
                "item_id": _ITEM_ID,
                "procurement_group": "PAS",
                "product_group": "XTAL",
            })
        assert r.status_code == 200
        body = r.json()
        assert body["procurement_group"] == "PAS"
        assert body["product_group"] == "XTAL"

    def test_multi_code_pair_without_commodity_override_still_writes(self):
        """PAS/RES has 4 codes but autofill-groups writes prgp/itcl only.
        Commodity code disambiguation happens at suggest-pn time (S3-2).
        This endpoint does NOT require a commodity_override."""
        updated = _mock_item(prgp="PAS", itcl="RES")
        with patch("src.routers.parts.ECNService") as MockSvc:
            svc = MockSvc.return_value
            svc.get_item = AsyncMock(return_value=_mock_item())
            svc.update_item = AsyncMock(return_value=updated)
            r = self._post({
                "ecn_id": _ECN_ID,
                "item_id": _ITEM_ID,
                "procurement_group": "PAS",
                "product_group": "RES",
            })
        assert r.status_code == 200
        assert r.json()["procurement_group"] == "PAS"
        assert r.json()["product_group"] == "RES"

    def test_em_connt_writes_correctly(self):
        """Connector (EM/CONNT) — common part type in ECNs."""
        updated = _mock_item(prgp="EM", itcl="CONNT")
        with patch("src.routers.parts.ECNService") as MockSvc:
            svc = MockSvc.return_value
            svc.get_item = AsyncMock(return_value=_mock_item())
            svc.update_item = AsyncMock(return_value=updated)
            r = self._post({
                "ecn_id": _ECN_ID,
                "item_id": _ITEM_ID,
                "procurement_group": "EM",
                "product_group": "CONNT",
            })
        assert r.status_code == 200

    def test_act_ic_writes_correctly(self):
        updated = _mock_item(prgp="ACT", itcl="IC")
        with patch("src.routers.parts.ECNService") as MockSvc:
            svc = MockSvc.return_value
            svc.get_item = AsyncMock(return_value=_mock_item())
            svc.update_item = AsyncMock(return_value=updated)
            r = self._post({
                "ecn_id": _ECN_ID,
                "item_id": _ITEM_ID,
                "procurement_group": "ACT",
                "product_group": "IC",
            })
        assert r.status_code == 200

    def test_input_case_normalised_to_upper(self):
        """lowercase prgp/itcl are normalised before write — engineers shouldn't need to know case."""
        updated = _mock_item(prgp="PAS", itcl="CAPS")
        with patch("src.routers.parts.ECNService") as MockSvc:
            svc = MockSvc.return_value
            svc.get_item = AsyncMock(return_value=_mock_item())
            svc.update_item = AsyncMock(return_value=updated)
            r = self._post({
                "ecn_id": _ECN_ID,
                "item_id": _ITEM_ID,
                "procurement_group": "pas",
                "product_group": "caps",
            })
        assert r.status_code == 200

    def test_update_item_called_with_correct_fields(self):
        """Verify ECNService.update_item is called with the right kwargs."""
        updated = _mock_item(prgp="PCB", itcl="RIGID")
        with patch("src.routers.parts.ECNService") as MockSvc:
            svc = MockSvc.return_value
            svc.get_item = AsyncMock(return_value=_mock_item())
            svc.update_item = AsyncMock(return_value=updated)
            self._post({
                "ecn_id": _ECN_ID,
                "item_id": _ITEM_ID,
                "procurement_group": "PCB",
                "product_group": "RIGID",
            })
            svc.update_item.assert_awaited_once_with(
                _ECN_ID, _ITEM_ID,
                procurement_group="PCB",
                product_group="RIGID",
            )

    def test_response_includes_commodity_codes(self):
        """Response includes the commodity_codes list for the written pair
        so the UI can immediately show which codes are available for suggest-pn."""
        updated = _mock_item(prgp="ACT", itcl="DIODE")
        with patch("src.routers.parts.ECNService") as MockSvc:
            svc = MockSvc.return_value
            svc.get_item = AsyncMock(return_value=_mock_item())
            svc.update_item = AsyncMock(return_value=updated)
            r = self._post({
                "ecn_id": _ECN_ID,
                "item_id": _ITEM_ID,
                "procurement_group": "ACT",
                "product_group": "DIODE",
            })
        assert r.status_code == 200
        body = r.json()
        assert "commodity_codes" in body
        assert sorted(body["commodity_codes"]) == ["24", "25"]

    # ── 422 validation — unknown pair ─────────────────────────────────────────

    def test_unknown_pair_returns_422(self):
        """Unknown (prgp, itcl) must be rejected before any DB write."""
        with patch("src.routers.parts.ECNService") as MockSvc:
            svc = MockSvc.return_value
            svc.get_item = AsyncMock(return_value=_mock_item())
            r = self._post({
                "ecn_id": _ECN_ID,
                "item_id": _ITEM_ID,
                "procurement_group": "ZZZ",
                "product_group": "UNKNOWN",
            })
        assert r.status_code == 422

    def test_known_prgp_unknown_itcl_returns_422(self):
        with patch("src.routers.parts.ECNService") as MockSvc:
            svc = MockSvc.return_value
            svc.get_item = AsyncMock(return_value=_mock_item())
            r = self._post({
                "ecn_id": _ECN_ID,
                "item_id": _ITEM_ID,
                "procurement_group": "PAS",
                "product_group": "INVALID",
            })
        assert r.status_code == 422

    def test_update_item_not_called_on_invalid_pair(self):
        """update_item must never be called when the pair is not in the matrix."""
        with patch("src.routers.parts.ECNService") as MockSvc:
            svc = MockSvc.return_value
            svc.get_item = AsyncMock(return_value=_mock_item())
            svc.update_item = AsyncMock()
            self._post({
                "ecn_id": _ECN_ID,
                "item_id": _ITEM_ID,
                "procurement_group": "ZZZ",
                "product_group": "NOPE",
            })
            svc.update_item.assert_not_awaited()

    # ── 404 — item not found ──────────────────────────────────────────────────

    def test_item_not_found_returns_404(self):
        from src.services.ecn import ECNNotFound
        with patch("src.routers.parts.ECNService") as MockSvc:
            svc = MockSvc.return_value
            svc.get_item = AsyncMock(side_effect=ECNNotFound(_ITEM_ID))
            r = self._post({
                "ecn_id": _ECN_ID,
                "item_id": _ITEM_ID,
                "procurement_group": "PAS",
                "product_group": "RES",
            })
        assert r.status_code == 404

    # ── 401 — auth required ───────────────────────────────────────────────────

    def test_requires_auth(self):
        """Unlike GET /groups, POST /autofill-groups requires a valid JWT."""
        r = _client_no_auth().post("/api/v1/parts/autofill-groups", json={
            "ecn_id": _ECN_ID,
            "item_id": _ITEM_ID,
            "procurement_group": "PAS",
            "product_group": "RES",
        })
        assert r.status_code == 401

    # ── Missing fields ────────────────────────────────────────────────────────

    def test_missing_procurement_group_returns_422(self):
        r = _client_with_auth().post("/api/v1/parts/autofill-groups", json={
            "ecn_id": _ECN_ID,
            "item_id": _ITEM_ID,
            "product_group": "RES",
        })
        assert r.status_code == 422

    def test_missing_product_group_returns_422(self):
        r = _client_with_auth().post("/api/v1/parts/autofill-groups", json={
            "ecn_id": _ECN_ID,
            "item_id": _ITEM_ID,
            "procurement_group": "PAS",
        })
        assert r.status_code == 422
