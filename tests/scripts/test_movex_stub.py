"""scripts/movex_stub.py — fixture-serving FastAPI stub for the external movex-rest-api
BOM contract (Slice 0, ADR-012). Used by e2e tests (MOVEX_API_URL pointed at a running
instance) and local dev; exercised here directly via TestClient.

Routes under test mirror docs/movex-rest-api-bom-contract.md: B-1 (GET /api/bom/{itno}).
"""

from fastapi.testclient import TestClient

from scripts.movex_stub import create_app

client = TestClient(create_app())


class TestBomHeadEndpoint:
    def test_known_item_returns_fixture_shape(self):
        resp = client.get("/api/bom/LF100001")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["head"]["PRNO"] == "LF100001"
        assert len(body["data"]["records"]) == 12

    def test_unknown_item_returns_404(self):
        resp = client.get("/api/bom/NOPE99999")

        assert resp.status_code == 404


class TestBomIndentedEndpoint:
    def test_known_item_returns_flat_levl_rows(self):
        resp = client.get("/api/bom/LF100001/indented")

        assert resp.status_code == 200
        records = resp.json()["data"]["records"]
        assert len(records) == 7
        assert {r["LEVL"] for r in records} == {1, 2, 3}

    def test_unknown_item_returns_404(self):
        resp = client.get("/api/bom/NOPE99999/indented")

        assert resp.status_code == 404


class TestWhereUsedEndpoint:
    def test_known_component_returns_parent_records(self):
        resp = client.get("/api/bom/where-used/LF200010")

        assert resp.status_code == 200
        records = resp.json()["data"]["records"]
        assert len(records) == 2
        assert {r["PRNO"] for r in records} == {"LF100001", "LF300001"}

    def test_unknown_component_returns_404(self):
        resp = client.get("/api/bom/where-used/NOPE99999")

        assert resp.status_code == 404


class TestCircuitRefsEndpoint:
    def test_known_item_returns_ref_des_records(self):
        resp = client.get("/api/bom/LF100001/circuit-refs")

        assert resp.status_code == 200
        records = resp.json()["data"]["records"]
        assert len(records) == 3
        assert records[0]["CIRF"] == ["R1", "R7", "R12"]

    def test_unknown_item_returns_404(self):
        resp = client.get("/api/bom/NOPE99999/circuit-refs")

        assert resp.status_code == 404


class TestBomMutationOverride:
    """e2e-only mutation endpoints (Slice E, ADR-012 R8) — not part of the
    real movex-rest-api contract. Lets ecn-bom-changes.spec.ts simulate a
    live Movex BOM change happening between an ECN's submit and its
    dc_approve, to exercise the DC concurrency gate end-to-end."""

    def test_mutate_then_reset_round_trip(self):
        original = client.get("/api/bom/LF100001").json()

        mutated = {
            "data": {
                "head": original["data"]["head"],
                "records": [
                    {**original["data"]["records"][0], "CNQT": 999.0},
                    *original["data"]["records"][1:],
                ],
            }
        }
        mutate_resp = client.post("/_test-mutate/bom/LF100001", json=mutated)
        assert mutate_resp.status_code == 200

        overridden = client.get("/api/bom/LF100001").json()
        assert overridden["data"]["records"][0]["CNQT"] == 999.0

        reset_resp = client.post("/_test-mutate/bom/LF100001/reset")
        assert reset_resp.status_code == 200

        restored = client.get("/api/bom/LF100001").json()
        assert restored == original

    def test_mutate_unknown_item_still_accepted(self):
        """The mutation endpoint doesn't require the item to already have a
        static fixture — an e2e test can invent a wholly synthetic BOM."""
        resp = client.post(
            "/_test-mutate/bom/LFE2ETEST1",
            json={"data": {"head": {"PRNO": "LFE2ETEST1"}, "records": []}},
        )
        assert resp.status_code == 200

        get_resp = client.get("/api/bom/LFE2ETEST1")
        assert get_resp.status_code == 200
        assert get_resp.json()["data"]["head"]["PRNO"] == "LFE2ETEST1"

        # Cleanup — leave shared module-level client state as found for
        # other tests in this file/session.
        client.post("/_test-mutate/bom/LFE2ETEST1/reset")


class TestMpmExportEndpoint:
    def test_default_page_returns_all_seven_raw_rows(self):
        resp = client.get("/api/mpm/export")

        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["total"] == 7
        assert len(body["records"]) == 7
        assert body["records"][0]["ITNO"] == " lf200010 "  # raw, untransformed — migration script cleans it

    def test_offset_and_limit_paginate(self):
        resp = client.get("/api/mpm/export", params={"offset": 5, "limit": 1000})

        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["offset"] == 5
        assert len(body["records"]) == 2
