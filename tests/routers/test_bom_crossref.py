"""
OSKAR — ECN BOM cross-reference advisory endpoint tests (Slice F, I2-12)

GET /api/v1/ecn/{ecn_id}/bom-crossref

Advisory: which OTHER live assemblies consume the components this ECN
deletes or supersedes. Never blocks — see src/services/bom/crossref.py.

Run with: pytest tests/routers/test_bom_crossref.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.adapters.erp.movex import MovexRestAdapter
from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app
from src.services.ecn import ECNNotFound

_STUB_ADAPTER = MovexRestAdapter.__new__(MovexRestAdapter)
app.state.erp_adapter = _STUB_ADAPTER

_ENGINEER = CurrentUser(
    username="eng_user",
    display_name="Test Engineer",
    email="eng@scanfil.com",
    groups=["ecn-initiator"],
    jti="test-jti-crossref-001",
)

_ECN_ID = "11111111-1111-1111-1111-111111111111"


def _make_client(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _change(change_id="c1", change_type="DELETE", component="LCAP010001", parent="LFAM050001"):
    c = MagicMock()
    c.id = change_id
    c.change_type = change_type
    c.component_number = component
    c.parent_item_number = parent
    return c


def _where_used_payload(*parents: str, component="LCAP010001"):
    return {
        "data": {
            "records": [
                {
                    "PRNO": p, "STRT": "001", "FACI": "D", "MSEQ": 10,
                    "MTNO": component, "OPNO": 10, "CNQT": 1.0, "PEUN": "PCS",
                    "FDAT": 20240101, "TDAT": 99999999,
                }
                for p in parents
            ]
        }
    }


def _call(changes, where_used_payload, facility_row=("D",)):
    with (
        patch("src.routers.ecn_bom.ECNService") as mock_svc_cls,
        patch.object(MovexRestAdapter, "get_where_used", new_callable=AsyncMock) as mock_wu,
        patch("src.routers.ecn_bom._ecn_facility", new_callable=AsyncMock) as mock_fac,
    ):
        mock_svc = MagicMock()
        mock_svc.list_all_bom_changes = AsyncMock(return_value=changes)
        mock_svc_cls.return_value = mock_svc
        mock_wu.return_value = where_used_payload
        mock_fac.return_value = facility_row[0]
        client = _make_client(_ENGINEER)
        return client.get(f"/api/v1/ecn/{_ECN_ID}/bom-crossref")


class TestCrossRefEndpoint:
    def test_returns_200(self):
        assert _call([_change()], _where_used_payload("OTHER001")).status_code == 200

    def test_reports_other_parents(self):
        resp = _call([_change()], _where_used_payload("OTHER001", "OTHER002"))
        body = resp.json()
        assert len(body) == 1
        assert body[0]["component_number"] == "LCAP010001"
        assert body[0]["other_parents"] == ["OTHER001", "OTHER002"]

    def test_empty_list_when_nothing_shared(self):
        resp = _call([_change()], _where_used_payload("LFAM050001"))
        assert resp.json() == []

    def test_add_changes_produce_no_findings(self):
        resp = _call([_change(change_type="ADD")], _where_used_payload("OTHER001"))
        assert resp.json() == []

    def test_finding_carries_change_id(self):
        resp = _call([_change(change_id="abc-123")], _where_used_payload("OTHER001"))
        assert resp.json()[0]["bom_change_id"] == "abc-123"

    def test_unknown_ecn_returns_404(self):
        with patch("src.routers.ecn_bom.ECNService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.list_all_bom_changes = AsyncMock(side_effect=ECNNotFound("nope"))
            mock_svc_cls.return_value = mock_svc
            client = _make_client(_ENGINEER)
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/bom-crossref")
        assert resp.status_code == 404

    def test_erp_outage_returns_200_with_check_failed(self):
        """The advisory must not 502 the review page — it reports that it
        could not check, which is different from 'all clear'."""
        with (
            patch("src.routers.ecn_bom.ECNService") as mock_svc_cls,
            patch.object(MovexRestAdapter, "get_where_used", new_callable=AsyncMock) as mock_wu,
            patch("src.routers.ecn_bom._ecn_facility", new_callable=AsyncMock) as mock_fac,
        ):
            mock_svc = MagicMock()
            mock_svc.list_all_bom_changes = AsyncMock(return_value=[_change()])
            mock_svc_cls.return_value = mock_svc
            mock_wu.side_effect = RuntimeError("circuit breaker open")
            mock_fac.return_value = "D"
            client = _make_client(_ENGINEER)
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/bom-crossref")

        assert resp.status_code == 200
        assert resp.json()[0]["check_failed"] is True

    def test_requires_authentication(self):
        app.dependency_overrides.clear()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(f"/api/v1/ecn/{_ECN_ID}/bom-crossref")
        assert resp.status_code in (401, 403)
