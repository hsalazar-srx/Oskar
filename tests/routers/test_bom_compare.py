"""
OSKAR — BOM compare endpoint tests (Slice D, ADR-012 D5).

POST /api/v1/bom/compare                    left/right descriptors + options
GET  /api/v1/bom/comparisons/{id}            fetch a saved comparison
POST /api/v1/bom/compare/upload              multipart upload -> customer-BOM compare
GET  /api/v1/bom/comparisons/{id}/export     xlsx export, fixed field set

Strategy matches tests/routers/test_mpn_search.py / test_parts_alias.py:
TestClient against the real app, service-layer functions patched at their
src.routers.bom import path (not the origin module) — no DB, no HTTP touched
in this test file. get_session is overridden to a stub since every route
here goes through the service layer, which is itself patched.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.adapters.erp.movex import MovexRestAdapter
from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app
from src.services.bom.comparisons import BOMComparison

# Seed app.state with a bare adapter instance so _get_erp_adapter resolves
# without starting the real lifespan — same convention as
# tests/routers/test_bom_browse.py / test_parts_alias.py.
app.state.erp_adapter = MovexRestAdapter.__new__(MovexRestAdapter)

_ENGINEER = CurrentUser(
    username="eng_user",
    display_name="Test Engineer",
    email="eng@scanfil.com",
    groups=["ecn-initiator"],
    jti="test-jti-bom-compare-001",
)


def _make_client(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


_SAVED_COMPARISON = BOMComparison(
    id="11111111-1111-1111-1111-111111111111",
    left_descriptor={"type": "erp", "item_number": "LF100001", "facility": "D"},
    right_descriptor={"type": "erp", "item_number": "LF100002", "facility": "D"},
    comparison_result={
        "added": [], "removed": [], "changed": [], "unresolved": [],
        "stats": {"left_count": 0, "right_count": 0, "added_count": 0,
                  "removed_count": 0, "changed_count": 0, "unresolved_count": 0},
    },
    cost_impact=None,
    risk_flags=[],
    created_by="eng_user",
    created_at=__import__("datetime").datetime(2026, 8, 1, tzinfo=__import__("datetime").timezone.utc),
)


class TestGetComparison:
    def test_existing_comparison_returns_200(self):
        with patch("src.routers.bom.get_comparison", new_callable=AsyncMock) as mock:
            mock.return_value = _SAVED_COMPARISON
            client = _make_client(_ENGINEER)
            resp = client.get(f"/api/v1/bom/comparisons/{_SAVED_COMPARISON.id}")

        assert resp.status_code == 200

    def test_response_includes_comparison_result(self):
        with patch("src.routers.bom.get_comparison", new_callable=AsyncMock) as mock:
            mock.return_value = _SAVED_COMPARISON
            client = _make_client(_ENGINEER)
            resp = client.get(f"/api/v1/bom/comparisons/{_SAVED_COMPARISON.id}")

        body = resp.json()
        assert body["id"] == _SAVED_COMPARISON.id
        assert body["comparison_result"]["stats"]["left_count"] == 0

    def test_unknown_id_returns_404(self):
        with patch("src.routers.bom.get_comparison", new_callable=AsyncMock) as mock:
            mock.return_value = None
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/comparisons/99999999-9999-9999-9999-999999999999")

        assert resp.status_code == 404

    def test_requires_authentication(self):
        app.dependency_overrides[get_session] = lambda: None
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(f"/api/v1/bom/comparisons/{_SAVED_COMPARISON.id}")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/bom/compare — left/right descriptors + options {key, fields[]}
# ---------------------------------------------------------------------------


class TestPostCompareERPvsERP:
    def test_erp_vs_erp_descriptors_returns_200(self):
        with patch("src.routers.bom.get_single_level_bom", new_callable=AsyncMock) as mock_bom, \
             patch("src.routers.bom.insert_comparison", new_callable=AsyncMock) as mock_insert:
            from src.services.bom.models import BOMHead, BOMLine

            mock_bom.side_effect = [
                BOMHead(item_number="LF100001", structure_type="001", facility="D",
                         description="A", lines=[
                             BOMLine(sequence_number=10, component_number="LF200010",
                                     description="R", operation_number=10, quantity=4.0,
                                     unit_of_measure="EA", from_date=20240101, to_date=99999999),
                         ]),
                BOMHead(item_number="LF100002", structure_type="001", facility="D",
                         description="B", lines=[
                             BOMLine(sequence_number=10, component_number="LF200010",
                                     description="R", operation_number=10, quantity=6.0,
                                     unit_of_measure="EA", from_date=20240101, to_date=99999999),
                         ]),
            ]
            mock_insert.return_value = _SAVED_COMPARISON

            client = _make_client(_ENGINEER)
            resp = client.post(
                "/api/v1/bom/compare",
                json={
                    "left": {"type": "erp", "item_number": "LF100001", "facility": "D"},
                    "right": {"type": "erp", "item_number": "LF100002", "facility": "D"},
                    "options": {},
                },
            )

        assert resp.status_code == 200

    def test_computed_diff_is_passed_to_insert_comparison(self):
        """insert_comparison is mocked (its own persistence is covered by
        tests/integration/test_bom_comparisons.py against real Postgres) —
        this test asserts the router actually computed the real diff and
        handed it to persistence, by inspecting the mock's call args rather
        than the (necessarily mocked) response body."""
        with patch("src.routers.bom.get_single_level_bom", new_callable=AsyncMock) as mock_bom, \
             patch("src.routers.bom.insert_comparison", new_callable=AsyncMock) as mock_insert:
            from src.services.bom.models import BOMHead, BOMLine

            mock_bom.side_effect = [
                BOMHead(item_number="LF100001", structure_type="001", facility="D",
                         description="A", lines=[
                             BOMLine(sequence_number=10, component_number="LF200010",
                                     description="R", operation_number=10, quantity=4.0,
                                     unit_of_measure="EA", from_date=20240101, to_date=99999999),
                         ]),
                BOMHead(item_number="LF100002", structure_type="001", facility="D",
                         description="B", lines=[
                             BOMLine(sequence_number=10, component_number="LF200010",
                                     description="R", operation_number=10, quantity=6.0,
                                     unit_of_measure="EA", from_date=20240101, to_date=99999999),
                         ]),
            ]
            mock_insert.return_value = _SAVED_COMPARISON

            client = _make_client(_ENGINEER)
            client.post(
                "/api/v1/bom/compare",
                json={
                    "left": {"type": "erp", "item_number": "LF100001", "facility": "D"},
                    "right": {"type": "erp", "item_number": "LF100002", "facility": "D"},
                    "options": {},
                },
            )

        _, kwargs = mock_insert.call_args
        assert kwargs["comparison_result"]["stats"]["changed_count"] == 1

    def test_persists_the_comparison(self):
        with patch("src.routers.bom.get_single_level_bom", new_callable=AsyncMock) as mock_bom, \
             patch("src.routers.bom.insert_comparison", new_callable=AsyncMock) as mock_insert:
            from src.services.bom.models import BOMHead

            mock_bom.side_effect = [
                BOMHead(item_number="LF100001", structure_type="001", facility="D", description="A", lines=[]),
                BOMHead(item_number="LF100002", structure_type="001", facility="D", description="B", lines=[]),
            ]
            mock_insert.return_value = _SAVED_COMPARISON

            client = _make_client(_ENGINEER)
            client.post(
                "/api/v1/bom/compare",
                json={
                    "left": {"type": "erp", "item_number": "LF100001", "facility": "D"},
                    "right": {"type": "erp", "item_number": "LF100002", "facility": "D"},
                    "options": {},
                },
            )

        assert mock_insert.await_count == 1

    def test_custom_key_and_fields_options_are_honoured(self):
        with patch("src.routers.bom.get_single_level_bom", new_callable=AsyncMock) as mock_bom, \
             patch("src.routers.bom.insert_comparison", new_callable=AsyncMock) as mock_insert:
            from src.services.bom.models import BOMHead, BOMLine

            mock_bom.side_effect = [
                BOMHead(item_number="LF100001", structure_type="001", facility="D",
                         description="A", lines=[
                             BOMLine(sequence_number=10, component_number="LF200010",
                                     description="Old desc", operation_number=10, quantity=4.0,
                                     unit_of_measure="EA", from_date=20240101, to_date=99999999),
                         ]),
                BOMHead(item_number="LF100002", structure_type="001", facility="D",
                         description="B", lines=[
                             BOMLine(sequence_number=10, component_number="LF200010",
                                     description="New desc", operation_number=20, quantity=4.0,
                                     unit_of_measure="EA", from_date=20240101, to_date=99999999),
                         ]),
            ]
            mock_insert.return_value = _SAVED_COMPARISON

            client = _make_client(_ENGINEER)
            client.post(
                "/api/v1/bom/compare",
                json={
                    "left": {"type": "erp", "item_number": "LF100001", "facility": "D"},
                    "right": {"type": "erp", "item_number": "LF100002", "facility": "D"},
                    "options": {"key": ["component_number"], "fields": ["operation_number"]},
                },
            )

        # component_number-only key matches the op-moved line -> 1 changed
        _, kwargs = mock_insert.call_args
        assert kwargs["comparison_result"]["stats"]["changed_count"] == 1

    def test_unknown_descriptor_type_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.post(
            "/api/v1/bom/compare",
            json={
                "left": {"type": "carrier_pigeon", "item_number": "LF100001"},
                "right": {"type": "erp", "item_number": "LF100002", "facility": "D"},
                "options": {},
            },
        )

        assert resp.status_code == 422

    def test_erp_left_not_found_returns_404(self):
        with patch("src.routers.bom.get_single_level_bom", new_callable=AsyncMock) as mock_bom:
            from src.adapters.erp.base import BOMNotFound

            mock_bom.side_effect = BOMNotFound("no BOM for LF999999")

            client = _make_client(_ENGINEER)
            resp = client.post(
                "/api/v1/bom/compare",
                json={
                    "left": {"type": "erp", "item_number": "LF999999", "facility": "D"},
                    "right": {"type": "erp", "item_number": "LF100002", "facility": "D"},
                    "options": {},
                },
            )

        assert resp.status_code == 404


class TestPostCompareSnapshotSide:
    def test_snapshot_descriptor_resolves_via_get_snapshot(self):
        with patch("src.routers.bom.get_snapshot", new_callable=AsyncMock) as mock_snap, \
             patch("src.routers.bom.get_single_level_bom", new_callable=AsyncMock) as mock_bom, \
             patch("src.routers.bom.insert_comparison", new_callable=AsyncMock) as mock_insert:
            from src.services.bom.models import BOMHead, BOMLine
            from src.services.bom.snapshots import BOMSnapshot
            import datetime

            mock_snap.return_value = BOMSnapshot(
                id="snap-1", item_number="LF100001", facility="D", structure_type="001",
                level_mode="single",
                lines=[{"component_number": "LF200010", "operation_number": 10, "quantity": 4.0}],
                line_count=1, content_hash="x" * 64, reason="manual", ecn_id=None,
                captured_by="eng_user", captured_at=datetime.datetime.now(datetime.timezone.utc),
            )
            mock_bom.return_value = BOMHead(
                item_number="LF100002", structure_type="001", facility="D", description="B", lines=[
                    BOMLine(sequence_number=10, component_number="LF200010",
                            description="R", operation_number=10, quantity=4.0,
                            unit_of_measure="EA", from_date=20240101, to_date=99999999),
                ],
            )
            mock_insert.return_value = _SAVED_COMPARISON

            client = _make_client(_ENGINEER)
            resp = client.post(
                "/api/v1/bom/compare",
                json={
                    "left": {"type": "snapshot", "snapshot_id": "snap-1"},
                    "right": {"type": "erp", "item_number": "LF100002", "facility": "D"},
                    "options": {},
                },
            )

        assert resp.status_code == 200
        mock_snap.assert_awaited_once()

    def test_unknown_snapshot_id_returns_404(self):
        with patch("src.routers.bom.get_snapshot", new_callable=AsyncMock) as mock_snap:
            mock_snap.return_value = None

            client = _make_client(_ENGINEER)
            resp = client.post(
                "/api/v1/bom/compare",
                json={
                    "left": {"type": "snapshot", "snapshot_id": "unknown-id"},
                    "right": {"type": "erp", "item_number": "LF100002", "facility": "D"},
                    "options": {},
                },
            )

        assert resp.status_code == 404
