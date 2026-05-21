"""
OSKAR — ECN items and MPN extended fields tests

POST   /api/v1/ecn/{ecn_id}/items               — Add item to ECN
GET    /api/v1/ecn/{ecn_id}/items               — List items with MPNs
GET    /api/v1/ecn/{ecn_id}/items/{item_id}     — Get single item
PATCH  /api/v1/ecn/{ecn_id}/items/{item_id}     — Update item fields
DELETE /api/v1/ecn/{ecn_id}/items/{item_id}     — Remove item

POST   /api/v1/ecn/{ecn_id}/items/{item_id}/mpns            — Add MPN
PATCH  /api/v1/ecn/{ecn_id}/items/{item_id}/mpns/{mpn_id}  — Update MPN (extended fields)
DELETE /api/v1/ecn/{ecn_id}/items/{item_id}/mpns/{mpn_id}  — Remove MPN

MPN extended fields (migration 0007, Engineering Team 2026-04-29):
  msl_level        SMALLINT 1–6
  lifecycle        'active' | 'eol' | 'nrnd'
  eol_date         DATE (ISO string)
  lead_time_weeks  SMALLINT
  packaging_type   'tape_reel' | 'tray' | 'tube' | 'cut_tape'
  do_not_buy       BOOLEAN
  alt_mpn          VARCHAR(100)
  supplier_data_at TIMESTAMPTZ

MPN + item fields (migration 0011, 2026-05-14):
  ecn_mpns.notes              TEXT (nullable) — ISO 13485 traceability for alt-MPN usage rationale
  ecn_items.customer_part_number  VARCHAR(50) (nullable) — customer's internal stock code, distinct from customer_alias

Strategy:
- FastAPI TestClient against real app.
- ECNService methods patched at the method level — no DB.
- get_current_user overridden via dependency_overrides.

TDD: written before ECNService item/MPN methods exist.

Run with: pytest tests/routers/test_ecn_items.py -v
"""
from __future__ import annotations

import dataclasses
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app
from src.services.ecn import ECNItemDetail, ECNMPNDetail, ECNService

_NOW = datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc)

_ENGINEER = CurrentUser(
    username="eng_user",
    display_name="Engineer",
    email="eng@scanfil.com",
    groups=["OSKAR-Engineers"],
    jti="test-jti-eng-001",
)

_ECN_ID = "ecn-uuid-items-001"
_ITEM_ID = "item-uuid-001"
_MPN_ID = "mpn-uuid-001"


# ── Shared fixture data (dataclasses — router calls _item_out/_mpn_out) ───────

_MPN_DETAIL = ECNMPNDetail(
    id=_MPN_ID,
    ecn_item_id=_ITEM_ID,
    mpn="PN-ACME-001",
    manufacturer="ACME Corp",
    is_default=True,
    alias_written=False,
    msl_level=3,
    lifecycle="active",
    eol_date="2029-12-31",
    lead_time_weeks=8,
    packaging_type="tape_reel",
    do_not_buy=False,
    alt_mpn=None,
    notes=None,
    supplier_data_at=None,
    created_at=_NOW,
)

_ITEM_DETAIL = ECNItemDetail(
    id=_ITEM_ID,
    ecn_id=_ECN_ID,
    line_number=1,
    is_new_item=True,
    item_number="LF-AA-001-0001",
    item_name="RESISTOR SMD",
    description_2=None,
    drawing_number=None,
    drawing_created=False,
    procurement_group="ELE",
    product_group=None,
    unit_of_measure="PCE",
    item_group="ELE",
    customer_alias="ACME-001",
    customer_part_number=None,
    effectivity_type="IMMEDIATE",
    effectivity_from=None,
    created_at=_NOW,
    updated_at=_NOW,
    mpns=[_MPN_DETAIL],
)


def _make_client(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ── POST /ecn/{ecn_id}/items ──────────────────────────────────────────────────

class TestCreateECNItem:
    """POST /api/v1/ecn/{ecn_id}/items"""

    def test_returns_201_with_item_detail(self):
        with patch.object(ECNService, "create_item", new_callable=AsyncMock) as mock:
            mock.return_value = _ITEM_DETAIL
            client = _make_client(_ENGINEER)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/items",
                json={
                    "line_number": 1,
                    "is_new_item": True,
                    "item_number": "LF-AA-001-0001",
                    "item_name": "RESISTOR SMD",
                    "effectivity_type": "IMMEDIATE",
                },
            )
        assert resp.status_code == 201
        assert resp.json()["id"] == _ITEM_ID
        assert resp.json()["item_number"] == "LF-AA-001-0001"

    def test_response_has_mpns_list(self):
        with patch.object(ECNService, "create_item", new_callable=AsyncMock) as mock:
            mock.return_value = _ITEM_DETAIL
            client = _make_client(_ENGINEER)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/items",
                json={
                    "line_number": 1,
                    "is_new_item": True,
                    "item_number": "LF-AA-001-0001",
                    "effectivity_type": "IMMEDIATE",
                },
            )
        assert "mpns" in resp.json()
        assert isinstance(resp.json()["mpns"], list)

    def test_missing_required_fields_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/items",
            json={"item_name": "RESISTOR SMD"},  # missing item_number, effectivity_type, line_number
        )
        assert resp.status_code == 422

    def test_invalid_effectivity_type_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/items",
            json={
                "line_number": 1,
                "item_number": "LF-AA-001-0001",
                "effectivity_type": "INVALID",
            },
        )
        assert resp.status_code == 422

    def test_no_jwt_returns_401(self):
        app.dependency_overrides.clear()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/items",
            json={"line_number": 1, "item_number": "X", "effectivity_type": "IMMEDIATE"},
        )
        assert resp.status_code == 401

    def test_calls_service_with_ecn_id(self):
        with patch.object(ECNService, "create_item", new_callable=AsyncMock) as mock:
            mock.return_value = _ITEM_DETAIL
            client = _make_client(_ENGINEER)
            client.post(
                f"/api/v1/ecn/{_ECN_ID}/items",
                json={
                    "line_number": 1,
                    "item_number": "LF-AA-001-0001",
                    "effectivity_type": "IMMEDIATE",
                },
            )
        mock.assert_awaited_once()
        assert mock.call_args.args[0] == _ECN_ID


# ── GET /ecn/{ecn_id}/items ───────────────────────────────────────────────────

class TestListECNItems:
    """GET /api/v1/ecn/{ecn_id}/items"""

    def test_returns_200_list(self):
        with patch.object(ECNService, "list_items", new_callable=AsyncMock) as mock:
            mock.return_value = [_ITEM_DETAIL]
            client = _make_client(_ENGINEER)
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/items")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) == 1

    def test_each_item_has_mpns(self):
        with patch.object(ECNService, "list_items", new_callable=AsyncMock) as mock:
            mock.return_value = [_ITEM_DETAIL]
            client = _make_client(_ENGINEER)
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/items")
        item = resp.json()[0]
        assert "mpns" in item
        assert item["mpns"][0]["mpn"] == "PN-ACME-001"

    def test_empty_list_when_no_items(self):
        with patch.object(ECNService, "list_items", new_callable=AsyncMock) as mock:
            mock.return_value = []
            client = _make_client(_ENGINEER)
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/items")
        assert resp.status_code == 200
        assert resp.json() == []


# ── GET /ecn/{ecn_id}/items/{item_id} ────────────────────────────────────────

class TestGetECNItem:
    """GET /api/v1/ecn/{ecn_id}/items/{item_id}"""

    def test_returns_200_item_detail(self):
        with patch.object(ECNService, "get_item", new_callable=AsyncMock) as mock:
            mock.return_value = _ITEM_DETAIL
            client = _make_client(_ENGINEER)
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}")
        assert resp.status_code == 200
        assert resp.json()["id"] == _ITEM_ID

    def test_item_not_found_returns_404(self):
        from src.services.ecn import ECNNotFound
        with patch.object(ECNService, "get_item", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNNotFound("item not found")
            client = _make_client(_ENGINEER)
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/items/no-such-item")
        assert resp.status_code == 404

    def test_mpns_contain_extended_fields(self):
        with patch.object(ECNService, "get_item", new_callable=AsyncMock) as mock:
            mock.return_value = _ITEM_DETAIL
            client = _make_client(_ENGINEER)
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}")
        mpn = resp.json()["mpns"][0]
        assert mpn["msl_level"] == 3
        assert mpn["lifecycle"] == "active"
        assert mpn["lead_time_weeks"] == 8
        assert mpn["packaging_type"] == "tape_reel"
        assert mpn["do_not_buy"] is False
        assert mpn["eol_date"] == "2029-12-31"

    def test_item_exposes_customer_part_number(self):
        detail = dataclasses.replace(_ITEM_DETAIL, customer_part_number="CMP-PN-001")
        with patch.object(ECNService, "get_item", new_callable=AsyncMock) as mock:
            mock.return_value = detail
            client = _make_client(_ENGINEER)
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}")
        assert resp.json()["customer_part_number"] == "CMP-PN-001"

    def test_item_customer_part_number_null_when_not_set(self):
        with patch.object(ECNService, "get_item", new_callable=AsyncMock) as mock:
            mock.return_value = _ITEM_DETAIL
            client = _make_client(_ENGINEER)
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}")
        assert resp.json()["customer_part_number"] is None

    def test_mpn_exposes_notes_field(self):
        mpn_with_notes = dataclasses.replace(
            _MPN_DETAIL,
            alt_mpn="PN-ACME-002",
            notes="Use PN-ACME-002 for AX8 Core only — NRND",
        )
        detail = dataclasses.replace(_ITEM_DETAIL, mpns=[mpn_with_notes])
        with patch.object(ECNService, "get_item", new_callable=AsyncMock) as mock:
            mock.return_value = detail
            client = _make_client(_ENGINEER)
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}")
        mpn = resp.json()["mpns"][0]
        assert mpn["notes"] == "Use PN-ACME-002 for AX8 Core only — NRND"
        assert mpn["alt_mpn"] == "PN-ACME-002"

    def test_mpn_notes_null_when_not_set(self):
        with patch.object(ECNService, "get_item", new_callable=AsyncMock) as mock:
            mock.return_value = _ITEM_DETAIL
            client = _make_client(_ENGINEER)
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}")
        assert resp.json()["mpns"][0]["notes"] is None


# ── PATCH /ecn/{ecn_id}/items/{item_id} ──────────────────────────────────────

class TestUpdateECNItem:
    """PATCH /api/v1/ecn/{ecn_id}/items/{item_id}"""

    def test_returns_200_updated_item(self):
        updated = dataclasses.replace(_ITEM_DETAIL, item_name="CAPACITOR SMD")
        with patch.object(ECNService, "update_item", new_callable=AsyncMock) as mock:
            mock.return_value = updated
            client = _make_client(_ENGINEER)
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}",
                json={"item_name": "CAPACITOR SMD"},
            )
        assert resp.status_code == 200
        assert resp.json()["item_name"] == "CAPACITOR SMD"

    def test_item_not_found_returns_404(self):
        from src.services.ecn import ECNNotFound
        with patch.object(ECNService, "update_item", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNNotFound("item not found")
            client = _make_client(_ENGINEER)
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/items/no-such",
                json={"item_name": "X"},
            )
        assert resp.status_code == 404

    def test_empty_patch_body_is_valid(self):
        with patch.object(ECNService, "update_item", new_callable=AsyncMock) as mock:
            mock.return_value = _ITEM_DETAIL
            client = _make_client(_ENGINEER)
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}",
                json={},
            )
        assert resp.status_code == 200


# ── DELETE /ecn/{ecn_id}/items/{item_id} ─────────────────────────────────────

class TestDeleteECNItem:
    """DELETE /api/v1/ecn/{ecn_id}/items/{item_id}"""

    def test_returns_204_on_success(self):
        with patch.object(ECNService, "delete_item", new_callable=AsyncMock) as mock:
            mock.return_value = None
            client = _make_client(_ENGINEER)
            resp = client.delete(f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}")
        assert resp.status_code == 204

    def test_item_not_found_returns_404(self):
        from src.services.ecn import ECNNotFound
        with patch.object(ECNService, "delete_item", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNNotFound("item not found")
            client = _make_client(_ENGINEER)
            resp = client.delete(f"/api/v1/ecn/{_ECN_ID}/items/no-such")
        assert resp.status_code == 404

    def test_validation_error_returns_422(self):
        from src.services.ecn import ECNValidationError
        with patch.object(ECNService, "delete_item", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNValidationError("Cannot delete item — ECN is not in DRAFT status")
            client = _make_client(_ENGINEER)
            resp = client.delete(f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}")
        assert resp.status_code == 422


# ── POST /ecn/{ecn_id}/items/{item_id}/mpns ──────────────────────────────────

class TestCreateMPN:
    """POST /api/v1/ecn/{ecn_id}/items/{item_id}/mpns"""

    def test_returns_201_with_mpn_detail(self):
        with patch.object(ECNService, "create_mpn", new_callable=AsyncMock) as mock:
            mock.return_value = _MPN_DETAIL
            client = _make_client(_ENGINEER)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/mpns",
                json={"mpn": "PN-ACME-001", "manufacturer": "ACME Corp", "is_default": True},
            )
        assert resp.status_code == 201
        assert resp.json()["id"] == _MPN_ID
        assert resp.json()["mpn"] == "PN-ACME-001"

    def test_response_includes_extended_fields(self):
        with patch.object(ECNService, "create_mpn", new_callable=AsyncMock) as mock:
            mock.return_value = _MPN_DETAIL
            client = _make_client(_ENGINEER)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/mpns",
                json={"mpn": "PN-ACME-001", "is_default": True},
            )
        body = resp.json()
        assert "msl_level" in body
        assert "lifecycle" in body
        assert "eol_date" in body
        assert "lead_time_weeks" in body
        assert "packaging_type" in body
        assert "do_not_buy" in body
        assert "alt_mpn" in body
        assert "notes" in body
        assert "supplier_data_at" in body

    def test_create_with_notes(self):
        mpn_with_notes = dataclasses.replace(
            _MPN_DETAIL,
            alt_mpn="PN-ACME-ALT",
            notes="Use alt only for Rev B boards",
        )
        with patch.object(ECNService, "create_mpn", new_callable=AsyncMock) as mock:
            mock.return_value = mpn_with_notes
            client = _make_client(_ENGINEER)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/mpns",
                json={
                    "mpn": "PN-ACME-001",
                    "alt_mpn": "PN-ACME-ALT",
                    "notes": "Use alt only for Rev B boards",
                },
            )
        assert resp.status_code == 201
        assert resp.json()["notes"] == "Use alt only for Rev B boards"

    def test_missing_mpn_field_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/mpns",
            json={"manufacturer": "ACME Corp"},  # missing mpn
        )
        assert resp.status_code == 422

    def test_create_with_extended_fields(self):
        extended_mpn = dataclasses.replace(_MPN_DETAIL, msl_level=1, lifecycle="eol", do_not_buy=True)
        with patch.object(ECNService, "create_mpn", new_callable=AsyncMock) as mock:
            mock.return_value = extended_mpn
            client = _make_client(_ENGINEER)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/mpns",
                json={
                    "mpn": "PN-ACME-001",
                    "is_default": True,
                    "msl_level": 1,
                    "lifecycle": "eol",
                    "do_not_buy": True,
                },
            )
        assert resp.status_code == 201
        assert resp.json()["lifecycle"] == "eol"
        assert resp.json()["do_not_buy"] is True

    def test_invalid_msl_level_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/mpns",
            json={"mpn": "PN-X", "msl_level": 7},  # must be 1–6
        )
        assert resp.status_code == 422

    def test_invalid_lifecycle_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/mpns",
            json={"mpn": "PN-X", "lifecycle": "obsolete"},  # not in enum
        )
        assert resp.status_code == 422

    def test_invalid_packaging_type_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/mpns",
            json={"mpn": "PN-X", "packaging_type": "bag"},  # not in enum
        )
        assert resp.status_code == 422

    def test_item_not_found_returns_404(self):
        from src.services.ecn import ECNNotFound
        with patch.object(ECNService, "create_mpn", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNNotFound("item not found")
            client = _make_client(_ENGINEER)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/items/no-such/mpns",
                json={"mpn": "PN-ACME-001"},
            )
        assert resp.status_code == 404

    def test_no_jwt_returns_401(self):
        app.dependency_overrides.clear()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/mpns",
            json={"mpn": "PN-ACME-001"},
        )
        assert resp.status_code == 401


# ── PATCH /ecn/{ecn_id}/items/{item_id}/mpns/{mpn_id} ───────────────────────

class TestUpdateMPN:
    """PATCH /api/v1/ecn/{ecn_id}/items/{item_id}/mpns/{mpn_id} — extended fields"""

    def test_returns_200_updated_mpn(self):
        updated = dataclasses.replace(_MPN_DETAIL, msl_level=2, lifecycle="nrnd", do_not_buy=True)
        with patch.object(ECNService, "update_mpn", new_callable=AsyncMock) as mock:
            mock.return_value = updated
            client = _make_client(_ENGINEER)
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/mpns/{_MPN_ID}",
                json={"msl_level": 2, "lifecycle": "nrnd", "do_not_buy": True},
            )
        assert resp.status_code == 200
        assert resp.json()["msl_level"] == 2
        assert resp.json()["lifecycle"] == "nrnd"
        assert resp.json()["do_not_buy"] is True

    def test_patch_alt_mpn(self):
        updated = dataclasses.replace(_MPN_DETAIL, alt_mpn="PN-ACME-002")
        with patch.object(ECNService, "update_mpn", new_callable=AsyncMock) as mock:
            mock.return_value = updated
            client = _make_client(_ENGINEER)
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/mpns/{_MPN_ID}",
                json={"alt_mpn": "PN-ACME-002"},
            )
        assert resp.status_code == 200
        assert resp.json()["alt_mpn"] == "PN-ACME-002"

    def test_patch_notes(self):
        updated = dataclasses.replace(
            _MPN_DETAIL,
            alt_mpn="PN-ACME-002",
            notes="NRND — use alt for new designs only",
        )
        with patch.object(ECNService, "update_mpn", new_callable=AsyncMock) as mock:
            mock.return_value = updated
            client = _make_client(_ENGINEER)
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/mpns/{_MPN_ID}",
                json={"notes": "NRND — use alt for new designs only"},
            )
        assert resp.status_code == 200
        assert resp.json()["notes"] == "NRND — use alt for new designs only"

    def test_patch_customer_part_number_on_item(self):
        updated = dataclasses.replace(_ITEM_DETAIL, customer_part_number="CMP-8509G-001")
        with patch.object(ECNService, "update_item", new_callable=AsyncMock) as mock:
            mock.return_value = updated
            client = _make_client(_ENGINEER)
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}",
                json={"customer_part_number": "CMP-8509G-001"},
            )
        assert resp.status_code == 200
        assert resp.json()["customer_part_number"] == "CMP-8509G-001"

    def test_patch_lead_time_weeks(self):
        updated = dataclasses.replace(_MPN_DETAIL, lead_time_weeks=12)
        with patch.object(ECNService, "update_mpn", new_callable=AsyncMock) as mock:
            mock.return_value = updated
            client = _make_client(_ENGINEER)
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/mpns/{_MPN_ID}",
                json={"lead_time_weeks": 12},
            )
        assert resp.status_code == 200
        assert resp.json()["lead_time_weeks"] == 12

    def test_mpn_not_found_returns_404(self):
        from src.services.ecn import ECNNotFound
        with patch.object(ECNService, "update_mpn", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNNotFound("mpn not found")
            client = _make_client(_ENGINEER)
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/mpns/no-such",
                json={"msl_level": 2},
            )
        assert resp.status_code == 404

    def test_invalid_msl_level_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.patch(
            f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/mpns/{_MPN_ID}",
            json={"msl_level": 0},  # must be 1–6
        )
        assert resp.status_code == 422

    def test_calls_service_with_mpn_id(self):
        with patch.object(ECNService, "update_mpn", new_callable=AsyncMock) as mock:
            mock.return_value = _MPN_DETAIL
            client = _make_client(_ENGINEER)
            client.patch(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/mpns/{_MPN_ID}",
                json={"lifecycle": "active"},
            )
        mock.assert_awaited_once()
        assert mock.call_args.args[1] == _MPN_ID


# ── DELETE /ecn/{ecn_id}/items/{item_id}/mpns/{mpn_id} ──────────────────────

class TestDeleteMPN:
    """DELETE /api/v1/ecn/{ecn_id}/items/{item_id}/mpns/{mpn_id}"""

    def test_returns_204_on_success(self):
        with patch.object(ECNService, "delete_mpn", new_callable=AsyncMock) as mock:
            mock.return_value = None
            client = _make_client(_ENGINEER)
            resp = client.delete(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/mpns/{_MPN_ID}"
            )
        assert resp.status_code == 204

    def test_mpn_not_found_returns_404(self):
        from src.services.ecn import ECNNotFound
        with patch.object(ECNService, "delete_mpn", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNNotFound("mpn not found")
            client = _make_client(_ENGINEER)
            resp = client.delete(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/mpns/no-such"
            )
        assert resp.status_code == 404
