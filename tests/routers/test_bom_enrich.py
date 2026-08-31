"""
OSKAR — BOM supplier-attribute enrichment endpoint tests (Slice F, I2-12)

POST /api/v1/bom/{item_number}/enrich

Cache-first, capped live lookups. See src/services/bom/enrich.py for why the
cap is the central constraint rather than a nicety.

Run with: pytest tests/routers/test_bom_enrich.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from src.adapters.erp.base import BOMNotFound
from src.adapters.erp.movex import MovexRestAdapter
from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app

_STUB_ADAPTER = MovexRestAdapter.__new__(MovexRestAdapter)
app.state.erp_adapter = _STUB_ADAPTER
app.state.supplier_adapters = []

_ENGINEER = CurrentUser(
    username="eng_user",
    display_name="Test Engineer",
    email="eng@scanfil.com",
    groups=["ecn-initiator"],
    jti="test-jti-enrich-001",
)

_PAYLOAD = {
    "data": {
        "head": {"PRNO": "LF100001", "STRT": "001", "FACI": "D", "ITDS": "Widget"},
        "records": [
            {"MSEQ": 10, "MTNO": "LF200010", "ITDS": "Resistor", "OPNO": 10,
             "CNQT": 4.0, "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999},
            {"MSEQ": 20, "MTNO": "LF200011", "ITDS": "Capacitor", "OPNO": 10,
             "CNQT": 8.0, "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999},
        ],
    }
}


def _make_client(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _call(url="/api/v1/bom/LF100001/enrich", enriched=None, bom_side_effect=None):
    with (
        patch.object(MovexRestAdapter, "get_bom", new_callable=AsyncMock) as mock_bom,
        patch("src.routers.bom.enrich_bom_components", new_callable=AsyncMock) as mock_enrich,
        patch("src.routers.bom.SupplierChain") as mock_chain_cls,
    ):
        if bom_side_effect:
            mock_bom.side_effect = bom_side_effect
        else:
            mock_bom.return_value = _PAYLOAD
        mock_chain_cls.return_value = MagicMock()
        mock_enrich.return_value = enriched if enriched is not None else []
        client = _make_client(_ENGINEER)
        resp = client.post(url)
        return resp, mock_enrich


def _component(seq=10, component="LF200010", mpn="MPN-1", status="enriched", attrs=None):
    c = MagicMock()
    c.sequence_number = seq
    c.component_number = component
    c.description = "desc"
    c.mpn = mpn
    c.status = status
    c.attributes = attrs if attrs is not None else {"lifecycle": "Active"}
    return c


class TestEnrichSuccess:
    def test_returns_200(self):
        resp, _ = _call(enriched=[_component()])
        assert resp.status_code == 200

    def test_returns_components(self):
        resp, _ = _call(enriched=[_component(), _component(seq=20, component="LF200011")])
        body = resp.json()
        assert len(body["components"]) == 2
        assert body["components"][0]["component_number"] == "LF200010"

    def test_component_carries_status_and_attributes(self):
        resp, _ = _call(enriched=[_component(attrs={"lifecycle": "Obsolete"})])
        c = resp.json()["components"][0]
        assert c["status"] == "enriched"
        assert c["attributes"]["lifecycle"] == "Obsolete"

    def test_summary_counts_by_status(self):
        """The caller needs to see at a glance whether enrichment was
        complete — a summary beats making them tally statuses themselves."""
        resp, _ = _call(enriched=[
            _component(status="enriched"),
            _component(seq=20, status="enriched"),
            _component(seq=30, status="no_mpn"),
            _component(seq=40, status="cap_reached"),
        ])
        summary = resp.json()["summary"]
        assert summary["enriched"] == 2
        assert summary["no_mpn"] == 1
        assert summary["cap_reached"] == 1

    def test_incomplete_flag_set_when_cap_reached(self):
        """Explicit, so a client does not have to know that cap_reached is
        the status that means 'run me again'."""
        resp, _ = _call(enriched=[_component(status="cap_reached")])
        assert resp.json()["incomplete"] is True

    def test_incomplete_false_when_everything_resolved(self):
        resp, _ = _call(enriched=[_component(status="enriched"), _component(seq=20, status="no_mpn")])
        assert resp.json()["incomplete"] is False

    def test_incomplete_flag_set_when_lookup_failed(self):
        """An outage also makes the result incomplete — distinct from
        no_mpn/not_found, which are real findings about the data."""
        resp, _ = _call(enriched=[_component(status="lookup_failed")])
        assert resp.json()["incomplete"] is True


class TestLookupCapParameter:
    def test_cap_is_passed_through(self):
        _, mock_enrich = _call(url="/api/v1/bom/LF100001/enrich?live_lookup_cap=5")
        assert mock_enrich.await_args.kwargs["live_lookup_cap"] == 5

    def test_cap_above_ceiling_is_rejected(self):
        """The cap exists to protect a shared daily budget — a caller must
        not be able to raise it arbitrarily from a query param."""
        resp, _ = _call(url="/api/v1/bom/LF100001/enrich?live_lookup_cap=99999")
        assert resp.status_code == 422

    def test_zero_cap_is_rejected(self):
        resp, _ = _call(url="/api/v1/bom/LF100001/enrich?live_lookup_cap=0")
        assert resp.status_code == 422

    def test_omitted_cap_uses_the_service_default(self):
        _, mock_enrich = _call()
        assert mock_enrich.await_args.kwargs["live_lookup_cap"] is None


class TestErrors:
    def test_bom_not_found_returns_404(self):
        resp, _ = _call(bom_side_effect=BOMNotFound("nope"))
        assert resp.status_code == 404

    def test_erp_connect_error_returns_502(self):
        resp, _ = _call(bom_side_effect=httpx.ConnectError("refused"))
        assert resp.status_code == 502

    def test_requires_authentication(self):
        app.dependency_overrides.clear()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/v1/bom/LF100001/enrich")
        assert resp.status_code in (401, 403)
