"""
OSKAR — ECN BOM change endpoints (Slice E, I2-6, ADR-012)

Endpoints:
  POST   /api/v1/ecn/{ecn_id}/items/{item_id}/bom-changes        — Add change
  GET    /api/v1/ecn/{ecn_id}/items/{item_id}/bom-changes        — List changes
  PATCH  /api/v1/ecn/{ecn_id}/items/{item_id}/bom-changes/{id}   — Update change
  DELETE /api/v1/ecn/{ecn_id}/items/{item_id}/bom-changes/{id}   — Remove change

CHANGE/DELETE change_type rows require old_from_date (identifies which live
Movex line is being superseded/closed at dc_approve, D6). Edits are blocked
once the ECN has reached DC_APPROVED (workflow-order sense — DC_APPROVED,
APPROVED, IMPLEMENTED, CLOSED — not the raw ECNStatus int value, since
DC_APPROVED=25 sits numerically before ENGINEERING_REVIEW=30/
MANAGEMENT_REVIEW=40 despite being reached after them, ADR-009), UNLESS the
caller is exercising the DC role (mirrors how role gates are checked
elsewhere, e.g. assign_role's actor_role != "DC" check in workflow.py).

Strategy mirrors tests/routers/test_routing_operations.py exactly: FastAPI
TestClient against the real app, ECNService methods patched at the method
level (no DB), get_current_user overridden via dependency_overrides.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app
from src.routers.ecn_bom import _get_erp_adapter
from src.services.ecn import ECNService
from src.services.ecn.models import BOMChangeResponse

_NOW = datetime(2026, 8, 7, 10, 0, 0, tzinfo=timezone.utc)

_ENGINEER = CurrentUser(
    username="eng_user",
    display_name="Engineer",
    email="eng@scanfil.com",
    groups=["ecn-initiator"],
    jti="test-jti-eng-bom",
)

_ECN_ID = "ecn-uuid-bom-001"
_ITEM_ID = "item-uuid-bom-001"
_CHANGE_ID = "bomchange-uuid-001"


def _make_change(
    id: str = _CHANGE_ID,
    change_type: str = "ADD",
    component_number: str = "LF200010",
    quantity: float | None = 4.0,
    unit_of_measure: str | None = "EA",
    operation_number: int | None = 10,
    sequence_number: int | None = None,
    from_date: int | None = 20260901,
    to_date: int | None = None,
    old_quantity: float | None = None,
    old_operation_number: int | None = None,
    old_from_date: int | None = None,
    old_to_date: int | None = None,
    circuit_refs_old: list[str] | None = None,
    circuit_refs_new: list[str] | None = None,
    snapshot_id: str | None = None,
) -> BOMChangeResponse:
    return BOMChangeResponse(
        id=id,
        ecn_id=_ECN_ID,
        parent_item_number="LF100001",
        change_type=change_type,
        component_number=component_number,
        quantity=quantity,
        unit_of_measure=unit_of_measure,
        operation_number=operation_number,
        sequence_number=sequence_number,
        from_date=from_date,
        to_date=to_date,
        bom_type="M",
        notes=None,
        old_quantity=old_quantity,
        old_operation_number=old_operation_number,
        old_from_date=old_from_date,
        old_to_date=old_to_date,
        circuit_refs_old=circuit_refs_old,
        circuit_refs_new=circuit_refs_new,
        snapshot_id=snapshot_id,
        movex_snapshot_at_review=None,
        created_at=_NOW,
        ecn_item_id=_ITEM_ID,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _StubERPAdapter:
    """Every parent resolves in Movex — the happy path for the ADR-014
    ECN-scoped route's existence check."""

    async def get_item(self, item_number: str) -> dict:
        return {"itno": item_number}


@pytest.fixture(autouse=True)
def _override_deps():
    app.dependency_overrides[get_current_user] = lambda: _ENGINEER
    app.dependency_overrides[get_session] = lambda: None
    app.dependency_overrides[_get_erp_adapter] = lambda: _StubERPAdapter()
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# POST /bom-changes — create
# ---------------------------------------------------------------------------

class TestCreateBomChange:
    def test_create_add_change_returns_201(self, client):
        change = _make_change(change_type="ADD")
        with patch.object(ECNService, "create_bom_change", new=AsyncMock(return_value=change)):
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/bom-changes",
                json={
                    "change_type": "ADD",
                    "component_number": "LF200010",
                    "quantity": 4.0,
                    "unit_of_measure": "EA",
                    "operation_number": 10,
                    "from_date": 20260901,
                },
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["change_type"] == "ADD"
        assert body["component_number"] == "LF200010"

    def test_create_change_type_requires_old_from_date_returns_422(self, client):
        """CHANGE without old_from_date is a validation error — service layer
        raises ECNValidationError, which the router maps to 422 (same
        convention as every other ECNValidationError mapping in this app)."""
        from src.services.ecn.models import ECNValidationError
        with patch.object(
            ECNService, "create_bom_change",
            new=AsyncMock(side_effect=ECNValidationError(
                "old_from_date is required for change_type CHANGE/DELETE"
            )),
        ):
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/bom-changes",
                json={
                    "change_type": "CHANGE",
                    "component_number": "LF200010",
                    "quantity": 6.0,
                    "from_date": 20260901,
                    # old_from_date deliberately omitted
                },
            )
        assert resp.status_code == 422

    def test_create_delete_change_requires_old_from_date_returns_422(self, client):
        from src.services.ecn.models import ECNValidationError
        with patch.object(
            ECNService, "create_bom_change",
            new=AsyncMock(side_effect=ECNValidationError(
                "old_from_date is required for change_type CHANGE/DELETE"
            )),
        ):
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/bom-changes",
                json={
                    "change_type": "DELETE",
                    "component_number": "LF200010",
                    # old_from_date deliberately omitted
                },
            )
        assert resp.status_code == 422

    def test_create_change_with_old_from_date_returns_201(self, client):
        change = _make_change(
            change_type="CHANGE", old_quantity=4.0, old_from_date=20240101, quantity=6.0,
        )
        with patch.object(ECNService, "create_bom_change", new=AsyncMock(return_value=change)):
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/bom-changes",
                json={
                    "change_type": "CHANGE",
                    "component_number": "LF200010",
                    "quantity": 6.0,
                    "from_date": 20260901,
                    "old_from_date": 20240101,
                    "old_quantity": 4.0,
                },
            )
        assert resp.status_code == 201
        assert resp.json()["change_type"] == "CHANGE"

    def test_invalid_change_type_returns_422(self, client):
        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/bom-changes",
            json={
                "change_type": "REPLACE",  # invalid — valid values are ADD, CHANGE, DELETE
                "component_number": "LF200010",
            },
        )
        assert resp.status_code == 422

    def test_edit_blocked_at_dc_approved_returns_422(self, client):
        from src.services.ecn.models import ECNValidationError
        with patch.object(
            ECNService, "create_bom_change",
            new=AsyncMock(side_effect=ECNValidationError(
                "BOM changes cannot be edited once the ECN has reached DC_APPROVED (DC role only)"
            )),
        ):
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/bom-changes",
                json={"change_type": "ADD", "component_number": "LF200010"},
            )
        assert resp.status_code == 422

    def test_ecn_not_found_returns_404(self, client):
        from src.services.ecn.models import ECNNotFound
        with patch.object(
            ECNService, "create_bom_change",
            new=AsyncMock(side_effect=ECNNotFound(_ECN_ID)),
        ):
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/bom-changes",
                json={"change_type": "ADD", "component_number": "LF200010"},
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /bom-changes — list
# ---------------------------------------------------------------------------

class TestListBomChanges:
    def test_list_returns_all_changes(self, client):
        changes = [
            _make_change(id="c-1", change_type="ADD", component_number="LF200010"),
            _make_change(id="c-2", change_type="DELETE", component_number="LF200020", old_from_date=20240101),
            _make_change(id="c-3", change_type="CHANGE", component_number="LF200030", old_from_date=20240101),
        ]
        with patch.object(ECNService, "list_bom_changes", new=AsyncMock(return_value=changes)):
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/bom-changes")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 3
        types = {c["change_type"] for c in body}
        assert types == {"ADD", "DELETE", "CHANGE"}

    def test_list_empty_returns_empty_array(self, client):
        with patch.object(ECNService, "list_bom_changes", new=AsyncMock(return_value=[])):
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/bom-changes")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# PATCH /bom-changes/{id} — update
# ---------------------------------------------------------------------------

class TestUpdateBomChange:
    def test_update_quantity_returns_200(self, client):
        updated = _make_change(quantity=8.0)
        with patch.object(ECNService, "update_bom_change", new=AsyncMock(return_value=updated)):
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/bom-changes/{_CHANGE_ID}",
                json={"quantity": 8.0},
            )
        assert resp.status_code == 200
        assert resp.json()["quantity"] == pytest.approx(8.0)

    def test_update_not_found_returns_404(self, client):
        from src.services.ecn.models import ECNNotFound
        with patch.object(
            ECNService, "update_bom_change",
            new=AsyncMock(side_effect=ECNNotFound(_CHANGE_ID)),
        ):
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/bom-changes/{_CHANGE_ID}",
                json={"quantity": 8.0},
            )
        assert resp.status_code == 404

    def test_update_blocked_at_dc_approved_without_dc_role_returns_422(self, client):
        from src.services.ecn.models import ECNValidationError
        with patch.object(
            ECNService, "update_bom_change",
            new=AsyncMock(side_effect=ECNValidationError(
                "BOM changes cannot be edited once the ECN has reached DC_APPROVED (DC role only)"
            )),
        ):
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/bom-changes/{_CHANGE_ID}",
                json={"quantity": 8.0},
            )
        assert resp.status_code == 422

    def test_update_allowed_at_dc_approved_with_dc_role(self, client):
        """DC role bypasses the post-DC_APPROVED edit lock — actor_role is
        passed as a query/body param the same way other DC-gated endpoints
        (assign_role) take actor_role."""
        updated = _make_change(quantity=9.0)
        with patch.object(ECNService, "update_bom_change", new=AsyncMock(return_value=updated)):
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/bom-changes/{_CHANGE_ID}",
                json={"quantity": 9.0, "actor_role": "DC"},
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# DELETE /bom-changes/{id}
# ---------------------------------------------------------------------------

class TestDeleteBomChange:
    def test_delete_returns_204(self, client):
        with patch.object(ECNService, "delete_bom_change", new=AsyncMock(return_value=None)):
            resp = client.delete(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/bom-changes/{_CHANGE_ID}"
            )
        assert resp.status_code == 204

    def test_delete_not_found_returns_404(self, client):
        from src.services.ecn.models import ECNNotFound
        with patch.object(
            ECNService, "delete_bom_change",
            new=AsyncMock(side_effect=ECNNotFound(_CHANGE_ID)),
        ):
            resp = client.delete(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/bom-changes/{_CHANGE_ID}"
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /{ecn_id}/bom-changes — ECN-scoped create, no item required (ADR-014)
# ---------------------------------------------------------------------------

class TestCreateEcnScopedBomChange:
    """The BOM-only path. Stargile's ZECNBOMS row is self-contained (its own
    BMPRNO parent, no FK to the items table) and the check requiring the
    parent to be an ECN item was written there and deliberately commented
    out — so Oskar drops it too, and adopts the rule Stargile did enforce:
    the parent must exist in Movex."""

    def test_create_without_item_returns_201(self, client):
        change = _make_change(change_type="ADD")
        change.ecn_item_id = None
        with patch.object(
            ECNService, "create_bom_change", new=AsyncMock(return_value=change)
        ) as mock:
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/bom-changes",
                json={
                    "change_type": "ADD",
                    "component_number": "LF200010",
                    "parent_item_number": "LF100001",
                    "quantity": 4.0,
                    "operation_number": 10,
                    "from_date": 20260901,
                },
            )
        assert resp.status_code == 201
        assert resp.json()["ecn_item_id"] is None
        # item_id must be passed as None so the service takes the BOM-only path
        assert mock.await_args.args[1] is None

    def test_parent_item_number_is_required(self, client):
        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/bom-changes",
            json={"change_type": "ADD", "component_number": "LF200010"},
        )
        assert resp.status_code == 422

    def test_parent_missing_from_movex_returns_422(self, client):
        """A nonexistent parent makes get_item return {} — the MI route reports
        not-found as HTTP 422 / success:false, which the adapter absorbs, so an
        empty dict is the signal rather than a raised 404. Verified live against
        CONO=300 (2026-08-25)."""

        class _MissingParentERP:
            async def get_item(self, item_number: str) -> dict:
                return {}

        app.dependency_overrides[_get_erp_adapter] = lambda: _MissingParentERP()
        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/bom-changes",
            json={
                "change_type": "ADD",
                "component_number": "LF200010",
                "parent_item_number": "NOSUCHITEM",
            },
        )
        assert resp.status_code == 422
        assert "does not exist in Movex" in resp.json()["detail"]

    def test_erp_circuit_breaker_returns_503(self, client):
        class _BreakerOpenERP:
            async def get_item(self, item_number: str):
                raise RuntimeError("circuit breaker is open")

        app.dependency_overrides[_get_erp_adapter] = lambda: _BreakerOpenERP()
        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/bom-changes",
            json={
                "change_type": "ADD",
                "component_number": "LF200010",
                "parent_item_number": "LF100001",
            },
        )
        assert resp.status_code == 503

    def test_ecn_not_found_returns_404(self, client):
        from src.services.ecn.models import ECNNotFound
        with patch.object(
            ECNService, "create_bom_change",
            new=AsyncMock(side_effect=ECNNotFound(_ECN_ID)),
        ):
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/bom-changes",
                json={
                    "change_type": "ADD",
                    "component_number": "LF200010",
                    "parent_item_number": "LF100001",
                },
            )
        assert resp.status_code == 404
