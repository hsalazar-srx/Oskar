"""
OSKAR — MPN-not-found → Create-ECN prefill endpoint tests (Slice F, I2-12)

GET /api/v1/mpn/prefill-ecn?mpn=...

Run with: pytest tests/routers/test_mpn_prefill.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app
from src.services.bom.mpn_prefill import MPNPrefill

app.state.supplier_adapters = []

_ENGINEER = CurrentUser(
    username="eng_user",
    display_name="Test Engineer",
    email="eng@scanfil.com",
    groups=["ecn-initiator"],
    jti="test-jti-prefill-001",
)


def _session(existing_row=None):
    result = MagicMock()
    result.first.return_value = existing_row
    s = AsyncMock()
    s.execute = AsyncMock(return_value=result)
    return s


def _make_client(user: CurrentUser, session):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _prefill(found=True):
    return MPNPrefill(
        ecn_draft={
            "title": "Add MPN NEW-1",
            "description": "Add manufacturer part number NEW-1 to the item master.",
            "facility": "L",
            "add_mpn": True,
        },
        staged_mpn={"mpn": "NEW-1", "is_default": True, "manufacturer": "YAGEO"},
        supplier_data_found=found,
        supplier_attributes={"description": "RES 10K"} if found else {},
    )


def _call(url="/api/v1/mpn/prefill-ecn?mpn=NEW-1", existing_row=None, prefill=None):
    session = _session(existing_row)
    with patch("src.routers.mpn.build_mpn_ecn_prefill", new_callable=AsyncMock) as mock:
        mock.return_value = prefill if prefill is not None else _prefill()
        client = _make_client(_ENGINEER, session)
        return client.get(url), mock


class TestPrefillSuccess:
    def test_returns_200(self):
        resp, _ = _call()
        assert resp.status_code == 200

    def test_returns_ecn_draft_with_add_mpn_scope(self):
        """The flag that routes this ECN to the SC reviewer — the thing most
        easily forgotten when doing it by hand."""
        resp, _ = _call()
        assert resp.json()["ecn_draft"]["add_mpn"] is True

    def test_returns_staged_mpn(self):
        resp, _ = _call()
        staged = resp.json()["staged_mpn"]
        assert staged["mpn"] == "NEW-1"
        assert staged["is_default"] is True

    def test_reports_supplier_data_found(self):
        resp, _ = _call()
        assert resp.json()["supplier_data_found"] is True

    def test_reports_supplier_data_missing(self):
        """Distinguishes 'no supplier knows this part' from 'we could not
        reach the suppliers' for the UI."""
        resp, _ = _call(prefill=_prefill(found=False))
        assert resp.json()["supplier_data_found"] is False

    def test_mpn_is_normalised_in_the_response(self):
        resp, _ = _call(url="/api/v1/mpn/prefill-ecn?mpn=new-1")
        assert resp.json()["mpn"] == "NEW-1"

    def test_facility_passes_through(self):
        _, mock = _call(url="/api/v1/mpn/prefill-ecn?mpn=NEW-1&facility=D")
        assert mock.await_args.kwargs["facility"] == "D"


class TestAlreadyExists:
    def test_existing_mpn_returns_409(self):
        """Offering to 'add' something already on file would create a
        duplicate ECN and hide the existing record."""
        resp, _ = _call(existing_row=("LF100001",))
        assert resp.status_code == 409

    def test_409_names_the_owning_item(self):
        resp, _ = _call(existing_row=("LF100001",))
        assert "LF100001" in resp.json()["detail"]

    def test_no_prefill_is_built_when_it_already_exists(self):
        """Must not spend a supplier API call resolving something we are
        about to reject."""
        _, mock = _call(existing_row=("LF100001",))
        mock.assert_not_awaited()


class TestValidation:
    def test_missing_mpn_returns_422(self):
        resp, _ = _call(url="/api/v1/mpn/prefill-ecn")
        assert resp.status_code == 422

    def test_overlong_mpn_returns_422(self):
        """item_mpns.mpn is VARCHAR(30)."""
        resp, _ = _call(url="/api/v1/mpn/prefill-ecn?mpn=" + "M" * 40)
        assert resp.status_code == 422

    def test_requires_authentication(self):
        app.dependency_overrides.clear()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/mpn/prefill-ecn?mpn=NEW-1")
        assert resp.status_code in (401, 403)
