"""
OSKAR — ECN items/routing/MPNs export endpoint tests.

GET /api/v1/ecn/{ecn_id}/items/export
GET /api/v1/ecn/{ecn_id}/routing/export
GET /api/v1/ecn/{ecn_id}/mpns/export

Strategy: FastAPI TestClient, ECNService list methods patched at the method
level (no DB). The IMPLEMENTED-status guard runs raw SQL directly against the
session (same shape as ecn_comments.py's _require_not_implemented) — no
service layer to patch for that part, so get_session is overridden with a
small fake session returning canned status/ecn_number rows, matching the
pattern validated in test_ecn_comments.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app
from src.services.ecn import ECNItemDetail, ECNMPNDetail, ECNService, RoutingOperationResponse
from src.services.ecn.models import BOMChangeResponse
from src.workflow.machine import ECNStatus

_NOW = datetime(2026, 8, 4, 10, 0, 0, tzinfo=timezone.utc)

_ENGINEER = CurrentUser(
    username="eng_user",
    display_name="Engineer",
    email="eng@scanfil.com",
    groups=["ecn-initiator"],
    jti="test-jti-export-001",
)

_ECN_ID = "ecn-uuid-export-001"
_ECN_NUMBER = "ECN-2026-L-0099"

_ITEM = ECNItemDetail(
    id="item-1", ecn_id=_ECN_ID, line_number=1, is_new_item=False,
    item_number="LF-001", item_name="Widget", description_2=None,
    drawing_number=None, drawing_created=False, procurement_group="ELE",
    product_group=None, unit_of_measure="PCE", item_group=None,
    customer_alias=None, customer_part_number=None, effectivity_type="IMMEDIATE",
    effectivity_from=None, created_at=_NOW, updated_at=_NOW, mounting_type=None,
    mpns=[],
)

_MPN = ECNMPNDetail(
    id="mpn-1", ecn_item_id="item-1", mpn="ABC123", manufacturer="Yageo",
    is_default=True, alias_written=False, msl_level=None, lifecycle=None,
    eol_date=None, lead_time_weeks=None, packaging_type=None, do_not_buy=False,
    alt_mpn=None, notes=None, supplier_data_at=None, created_at=_NOW,
    item_number="LF-001", line_number=1,
)

_ROUTING_OP = RoutingOperationResponse(
    id="op-1", ecn_item_id="item-1", operation_number=10,
    operation_description="SMT placement", work_centre="SMT01", run_time=120.0,
    setup_time=30.0, change_type="ADD", movex_snapshot=None,
    created_at=_NOW, updated_at=_NOW, item_number="LF-001", line_number=1,
)

_BOM_CHANGE = BOMChangeResponse(
    id="bc-1", ecn_id="ecn-1", parent_item_number="LF-001",
    change_type="ADD", component_number="LF200010",
    quantity=4.0, unit_of_measure="EA", operation_number=10, sequence_number=None,
    from_date=20260901, to_date=None, bom_type="M", notes=None,
    old_quantity=None, old_operation_number=None, old_from_date=None, old_to_date=None,
    circuit_refs_old=None, circuit_refs_new=None, snapshot_id=None,
    movex_snapshot_at_review=None, created_at=_NOW,
    ecn_item_id="item-1", item_number="LF-001",
)


class _FakeResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def first(self):
        return self._rows[0] if self._rows else None


def _fake_session(status_row) -> AsyncMock:
    """A session whose first .execute() call returns the given (status, ecn_number) row."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_FakeResult(rows=[status_row] if status_row else []))
    return session


def _client(user: CurrentUser, session: AsyncMock) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


class TestExportItems:
    def test_returns_xlsx_when_implemented(self):
        session = _fake_session((ECNStatus.IMPLEMENTED, _ECN_NUMBER))
        client = _client(_ENGINEER, session)
        with patch.object(ECNService, "list_items", new_callable=AsyncMock) as mock:
            mock.return_value = [_ITEM]
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/items/export")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert f"{_ECN_NUMBER}-items.xlsx" in resp.headers["content-disposition"]
        assert len(resp.content) > 0

    def test_403_when_not_implemented(self):
        session = _fake_session((ECNStatus.DRAFT, _ECN_NUMBER))
        client = _client(_ENGINEER, session)
        resp = client.get(f"/api/v1/ecn/{_ECN_ID}/items/export")
        assert resp.status_code == 403
        assert "Movex Updated" in resp.json()["detail"]

    def test_404_when_ecn_missing(self):
        session = _fake_session(None)
        client = _client(_ENGINEER, session)
        resp = client.get(f"/api/v1/ecn/{_ECN_ID}/items/export")
        assert resp.status_code == 404


class TestExportRouting:
    def test_returns_xlsx_when_implemented(self):
        session = _fake_session((ECNStatus.IMPLEMENTED, _ECN_NUMBER))
        client = _client(_ENGINEER, session)
        with patch.object(ECNService, "list_all_routing_operations", new_callable=AsyncMock) as mock:
            mock.return_value = [_ROUTING_OP]
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/routing/export")

        assert resp.status_code == 200
        assert f"{_ECN_NUMBER}-routing.xlsx" in resp.headers["content-disposition"]

    def test_403_when_not_implemented(self):
        session = _fake_session((ECNStatus.ENGINEERING_REVIEW, _ECN_NUMBER))
        client = _client(_ENGINEER, session)
        resp = client.get(f"/api/v1/ecn/{_ECN_ID}/routing/export")
        assert resp.status_code == 403

    def test_404_when_ecn_missing(self):
        session = _fake_session(None)
        client = _client(_ENGINEER, session)
        resp = client.get(f"/api/v1/ecn/{_ECN_ID}/routing/export")
        assert resp.status_code == 404


class TestExportMPNs:
    def test_returns_xlsx_when_implemented(self):
        session = _fake_session((ECNStatus.IMPLEMENTED, _ECN_NUMBER))
        client = _client(_ENGINEER, session)
        with patch.object(ECNService, "list_all_mpns", new_callable=AsyncMock) as mock:
            mock.return_value = [_MPN]
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/mpns/export")

        assert resp.status_code == 200
        assert f"{_ECN_NUMBER}-mpns.xlsx" in resp.headers["content-disposition"]

    def test_403_when_not_implemented(self):
        session = _fake_session((ECNStatus.APPROVED, _ECN_NUMBER))
        client = _client(_ENGINEER, session)
        resp = client.get(f"/api/v1/ecn/{_ECN_ID}/mpns/export")
        assert resp.status_code == 403

    def test_404_when_ecn_missing(self):
        session = _fake_session(None)
        client = _client(_ENGINEER, session)
        resp = client.get(f"/api/v1/ecn/{_ECN_ID}/mpns/export")
        assert resp.status_code == 404


class TestListAllBomChanges:
    """GET /ecn/{ecn_id}/bom-changes — ECN-wide aggregate, for the ECN
    detail view's BOM Changes tab (Slice E, I2-6) — mirrors
    list_all_routing_operations/list_all_mpns."""

    def test_returns_200_with_changes(self):
        session = _fake_session((ECNStatus.DRAFT, _ECN_NUMBER))
        client = _client(_ENGINEER, session)
        with patch.object(ECNService, "list_all_bom_changes", new_callable=AsyncMock) as mock:
            mock.return_value = [_BOM_CHANGE]
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/bom-changes")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["component_number"] == "LF200010"
        assert body[0]["item_number"] == "LF-001"


class TestExportBomChanges:
    def test_returns_xlsx_when_implemented(self):
        session = _fake_session((ECNStatus.IMPLEMENTED, _ECN_NUMBER))
        client = _client(_ENGINEER, session)
        with patch.object(ECNService, "list_all_bom_changes", new_callable=AsyncMock) as mock:
            mock.return_value = [_BOM_CHANGE]
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/bom-changes/export")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert f"{_ECN_NUMBER}-bom-changes.xlsx" in resp.headers["content-disposition"]
        assert len(resp.content) > 0

    def test_403_when_not_implemented(self):
        session = _fake_session((ECNStatus.DRAFT, _ECN_NUMBER))
        client = _client(_ENGINEER, session)
        resp = client.get(f"/api/v1/ecn/{_ECN_ID}/bom-changes/export")
        assert resp.status_code == 403

    def test_404_when_ecn_missing(self):
        session = _fake_session(None)
        client = _client(_ENGINEER, session)
        resp = client.get(f"/api/v1/ecn/{_ECN_ID}/bom-changes/export")
        assert resp.status_code == 404
