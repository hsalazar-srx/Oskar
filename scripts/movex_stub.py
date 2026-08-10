"""Fixture-serving FastAPI stub for the external movex-rest-api BOM contract.

Slice 0 (ADR-012, D7): e2e tests point MOVEX_API_URL at a running instance of this
stub instead of the real .NET movex-rest-api. Local dev can run it the same way.
Routes mirror docs/movex-rest-api-bom-contract.md; response shapes are the fixture
files verbatim (they're already authored in the `{data: {...}}` envelope the real
API uses).

Run standalone:
    uvicorn scripts.movex_stub:app --port 8100

Point Oskar at it:
    MOVEX_API_URL=http://localhost:8100
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

_DEFAULT_FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "bom"

# B-1: GET /api/bom/{itno} — MPDHED head + MPDMAT lines
_BOM_FIXTURES = {
    "LF100001": "single_level.json",
    "LF100002": "expired_lines.json",
    "LF900001": "large_500.json",
}

# B-2: GET /api/bom/{itno}/indented — recursive CTE, flat depth-first LEVL rows
_BOM_INDENTED_FIXTURES = {
    "LF100001": "multi_level.json",
}

# B-3: GET /api/bom/where-used/{mtno} — reverse MPDMAT on PMMTNO
_WHERE_USED_FIXTURES = {
    "LF200010": "where_used.json",
}

# C-1: GET /api/bom/{prno}/circuit-refs — ZECNCIRF read (migration/backfill only)
_CIRCUIT_REFS_FIXTURES = {
    "LF100001": "ref_des.json",
}

# M-1: GET /api/mpm/export — paged ZECNMPMS dump, migration only. Rows are raw
# (untransformed) — TRIM/uppercase/date-null/synonym normalisation is the
# migration script's job (Slice C), not this stub's.
_ZECNMPMS_FIXTURE = "zecnmpms_sample.csv"


def _load_fixture(fixtures_dir: Path, fixture_map: dict[str, str], key: str, *, not_found_label: str) -> dict:
    filename = fixture_map.get(key)
    if filename is None:
        raise HTTPException(status_code=404, detail=f"no {not_found_label} for {key!r}")
    return json.loads((fixtures_dir / filename).read_text())


def create_app(fixtures_dir: Path | None = None) -> FastAPI:
    fixtures_dir = fixtures_dir or _DEFAULT_FIXTURES_DIR
    app = FastAPI(title="movex-rest-api BOM contract stub")

    # In-memory override store (Slice E e2e need, ecn-bom-changes.spec.ts):
    # not part of the real movex-rest-api contract — the "_test-" prefix and
    # separate mutation namespace make that unambiguous. Lets an e2e test
    # simulate "someone else changed the live Movex BOM between this ECN's
    # submit and its dc_approve" without needing an actual M3 write, which
    # is exactly the DC concurrency-gate scenario (ADR-012 R8) the spec
    # exercises. GET /api/bom/{itno} checks this override before falling
    # back to the static fixture file.
    _bom_overrides: dict[str, dict[str, Any]] = {}

    @app.get("/api/bom/{itno}")
    def get_bom(itno: str) -> dict:
        if itno in _bom_overrides:
            return _bom_overrides[itno]
        return _load_fixture(fixtures_dir, _BOM_FIXTURES, itno, not_found_label="BOM")

    @app.post("/_test-mutate/bom/{itno}")
    def test_mutate_bom(itno: str, payload: dict) -> dict:
        """e2e-only: overrides itno's GET /api/bom/{itno} response until
        reset. Not part of the real movex-rest-api contract (see docstring
        above) — used by ecn-bom-changes.spec.ts to mutate the live BOM
        mid-test, simulating a real Movex write happening between an ECN's
        submit and dc_approve."""
        _bom_overrides[itno] = payload
        return {"status": "ok", "itno": itno}

    @app.post("/_test-mutate/bom/{itno}/reset")
    def test_reset_bom(itno: str) -> dict:
        """e2e-only: clears itno's override, reverting to the static fixture."""
        _bom_overrides.pop(itno, None)
        return {"status": "ok", "itno": itno}

    @app.get("/api/bom/{itno}/indented")
    def get_bom_indented(itno: str) -> dict:
        return _load_fixture(fixtures_dir, _BOM_INDENTED_FIXTURES, itno, not_found_label="indented BOM")

    @app.get("/api/bom/where-used/{mtno}")
    def get_where_used(mtno: str) -> dict:
        return _load_fixture(fixtures_dir, _WHERE_USED_FIXTURES, mtno, not_found_label="where-used records")

    @app.get("/api/bom/{prno}/circuit-refs")
    def get_circuit_refs(prno: str) -> dict:
        return _load_fixture(fixtures_dir, _CIRCUIT_REFS_FIXTURES, prno, not_found_label="circuit refs")

    @app.get("/api/mpm/export")
    def get_mpm_export(offset: int = 0, limit: int = 1000) -> dict:
        with (fixtures_dir / _ZECNMPMS_FIXTURE).open(newline="") as f:
            rows = list(csv.DictReader(f))
        page = rows[offset : offset + limit]
        return {"data": {"records": page, "offset": offset, "limit": limit, "total": len(rows)}}

    return app


app = create_app()
