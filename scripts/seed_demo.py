"""
OSKAR Demo Seed Script
======================
Creates a realistic set of ECNs at every workflow stage for local demos and UAT.

Usage (inside the app container):
    docker exec oskar-app-dev python scripts/seed_demo.py

Or directly if you have Python + deps installed on the host:
    python scripts/seed_demo.py

What it creates
---------------
1. DRAFT              — "SMT line capacitor substitution"        (hsalazar)
2. ENGINEERING_REVIEW — "Replace connector J4 on PCB-A-001"     (hsalazar, submitted)
3. MANAGEMENT_REVIEW  — "New IC — LM2596 buck converter"         (hsalazar, SE approved)
4. DC_APPROVED        — "Routing change — remove wave solder op" (hsalazar, full approval)
5. APPROVED           — "BOM rationalisation — Q2 2026"          (hsalazar, DC approved)
6. REJECTED           — "Add conformal coating step"             (eng_user, rejected by SE)
7. ON_HOLD            — "Supplier change — TDK to Murata"        (held by DC from MGMT_REVIEW)
8. CLOSED             — "Phase 1 EOL component swap"             (hsalazar, archived)
9. DRAFT (BOM)        — "BOM changes — Widget Assembly A rev"    (hsalazar, ADD/CHANGE/DELETE lines)
10. DC_APPROVED (BOM)  — "BOM supersession — connector swap"      (hsalazar, full write-back chain)
11. DC_APPROVED (blocked) — "BOM change blocked by live conflict"    (hsalazar, dc_approve fails — see below)

ECNs 9-11 exercise the BOM module (Slice E) against item LF100001, the item
tests/fixtures/bom/single_level.json and scripts/movex_stub.py both key off.
They need a reachable ERP endpoint (MOVEX_API_URL) to show their full
behaviour — the script probes it once at startup (see "BOM demo notes" below)
and degrades gracefully (matching production's own resilience design) if
nothing answers: the ECNs still get created and still carry their BOM change
rows, they just won't have gone through a real snapshot/concurrency check.

Each ECN has:
  - 1–3 line items with realistic part numbers and descriptions
  - MPNs with manufacturer references where relevant
  - Routing operations (where routing_changes=True)
  - Full audit chain (real transitions via ECNService — not raw SQL)

BOM demo notes (ECNs 9-11)
---------------------------
The script probes MOVEX_API_URL once at startup (a real GET /bom/LF100001,
not health_check() — movex_stub.py has no /health route):
  - Reachable   -> ECN 10 goes through a real submit-time snapshot + dc_approve
                   concurrency re-fetch; ECN 11 is set up by actually POSTing
                   to the stub's /_test-mutate/bom/LF100001 endpoint between
                   submit and dc_approve so the conflict is real, not staged.
                   Point MOVEX_API_URL at scripts/movex_stub.py for this —
                   the real movex-rest-api doesn't expose /_test-mutate and
                   W-1 (UpdComponent) isn't built there yet (I2-19), so the
                   real API is NOT a safe target for ECN 10/11's dc_approve.
  - Unreachable -> both ECNs still get created with the same bom_changes
                   rows; the snapshot/concurrency-gate calls skip themselves
                   with a logged warning (production's own degrade-gracefully
                   behaviour — see ecn.bom_snapshot.capture_failed /
                   ecn.bom_concurrency.skipped_no_erp_adapter in workflow.py),
                   so ECN 10 simply reaches DC_APPROVED without ever having
                   compared against a live BOM, and ECN 10 is skipped
                   entirely (there's nothing to conflict against).
Run the stub first if you want the full story:
    uvicorn scripts.movex_stub:app --port 8100
    MOVEX_API_URL=http://localhost:8100 MOVEX_CONO=300 python scripts/seed_demo.py

MOVEX_CONO is required as well as MOVEX_API_URL — MovexRestAdapter() reads both
from the environment and raises KeyError without them, *after* the eight
non-BOM ECNs have already been created. From a Windows host, also point
DATABASE_URL at localhost (the container hostname oskar-db-dev does not resolve):
    DATABASE_URL=postgresql+asyncpg://oskar:oskar_dev@localhost:5432/oskar

Idempotent: deletes existing demo ECNs by title prefix "[DEMO]" before re-creating.
Safe to run against dev DB. Never touches the test DB (port 5433).

Role reference (all roles seeded with 3 users per role for facility D (Melbourne) and L (Johor Bahru)):
  DC  Document Controller  — coordinates all gates
  SE  Senior Engineer      — technical review (Engineering Review stage)
  CE  Chief Engineer       — escalation co-reviewer alongside SE
  EM  Engineering Manager  — mandatory Management Review approver
  QM  Quality Manager      — mandatory Management Review approver (ISO 13485)
  PM  Production Manager   — conditional: routing_changes or operation_changes
  SC  Supply Chain         — conditional: new_parts or lead_time_changes
  FN  Finance              — conditional: wapc_delta_pct > threshold
  CA  Cost Accountant      — cost observer; no veto
  AD  Administrator        — platform admin; place-on-hold and override
  RD  R&D / Product Eng.   — observer; notified when product family affected
  TE  Test Engineering     — observer; notified when change_to_documents=TRUE
  MQ  Manufacturing Quality— observer; notified at CLOSED

Demo login personas (all in DEV_USERS, no LDAP needed):
  hsalazar   Hector Salazar       — Originator / also DC for demo
  eng_user   Nick Lim             — Senior Engineer (SE)
  qm_user    Divya Sharma         — Quality Manager (QM)
  dc_user    Karen Tan            — Document Controller (DC, backup)
  em_user    Karen Chen           — Engineering Manager (EM)
  ce_user    Branko Petrovic      — Chief Engineer (CE)
  pm_user    Jason Teo            — Production Manager (PM)
  sc_user    Michelle Tan         — Supply Chain Manager (SC)
  fn_user    Grace Lau            — Finance Manager (FN)
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, timedelta

# This script prints ✓/✗ status marks. On a Windows host the console defaults to
# cp1252 and those raise UnicodeEncodeError, masking the real error behind an
# encoding traceback (the container's stdout is UTF-8, so it only bites on the host).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Allow running from project root inside Docker (/app) or Windows host
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.adapters.erp.movex import MovexRestAdapter
from src.services.ecn.models import (
    BOMChangeRequest,
    ECNCreateRequest,
    ECNStatusTransitionRequest,
    RoutingOperationRequest,
)
from src.services.ecn.service import ECNService

# ---------------------------------------------------------------------------
# DB connection — always the dev DB, never the test DB
# ---------------------------------------------------------------------------

_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://oskar:oskar_dev@oskar-db-dev:5432/oskar",
).replace("?ssl=disable", "")

if "ssl=" not in _DB_URL:
    _DB_URL += "?ssl=disable"


# ---------------------------------------------------------------------------
# Personas — primary actor per role used during ECN transitions
# ---------------------------------------------------------------------------

OR = "hsalazar"    # Originator / also DC for demo simplicity
SE = "eng_user"    # Senior Engineer
QM = "qm_user"     # Quality Manager
DC = "dc_user"     # Document Controller (backup — hsalazar is primary)
EM = "em_user"     # Engineering Manager
CE = "ce_user"     # Chief Engineer
PM = "pm_user"     # Production Manager
SC = "sc_user"     # Supply Chain Manager
FN = "fn_user"     # Finance Manager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _wipe_demo_ecns(session: AsyncSession) -> int:
    """Delete all ECNs whose title starts with [DEMO]. Returns count deleted."""
    result = await session.execute(
        sa.text("SELECT id FROM ecn_instances WHERE title LIKE '[DEMO]%'")
    )
    ids = [str(r[0]) for r in result]
    if not ids:
        return 0
    for ecn_id in ids:
        # routing_operations, mpns, and bom_changes hang off ecn_items, not ecn_id directly
        await session.execute(
            sa.text(
                "DELETE FROM ecn_routing_operations WHERE ecn_item_id IN "
                "(SELECT id FROM ecn_items WHERE ecn_id = :id)"
            ),
            {"id": ecn_id},
        )
        await session.execute(
            sa.text(
                "DELETE FROM ecn_mpns WHERE ecn_item_id IN "
                "(SELECT id FROM ecn_items WHERE ecn_id = :id)"
            ),
            {"id": ecn_id},
        )
        await session.execute(
            sa.text(
                "DELETE FROM ecn_bom_changes WHERE ecn_item_id IN "
                "(SELECT id FROM ecn_items WHERE ecn_id = :id)"
            ),
            {"id": ecn_id},
        )
        for tbl in (
            "ecn_transition_history",
            "ecn_rejections",
            "ecn_approval_steps",
            "ecn_role_assignments",
            # movex_outbox before ecn_items: fk_outbox_item (0001_initial_schema.py)
            # references ecn_items.id — rows left pending (no Celery worker
            # running against this seed) still hold that FK on re-run.
            "movex_outbox",
            "ecn_items",
        ):
            await session.execute(
                sa.text(f"DELETE FROM {tbl} WHERE ecn_id = :id"), {"id": ecn_id}
            )
        await session.execute(
            sa.text("DELETE FROM ecn_instances WHERE id = :id"), {"id": ecn_id}
        )
    return len(ids)


async def _ensure_role_users(session: AsyncSession) -> None:
    """Seed 3 users per role for facilities D (Melbourne, primary) and L (Johor Bahru).

    _auto_assign_roles uses the first row per (facility, role_id) ordered by
    insertion order when exactly one is configured. With multiple rows it sets
    username=None — which is correct: DC manually assigns the specific engineer.

    The first row per role is the canonical demo actor used in ECN builders above.
    """
    await session.execute(
        sa.text("DELETE FROM system_role_users WHERE facility IN ('D', 'L')")
    )

    # (facility, role_id, username, display_name)
    # First row per role = primary actor used in demo ECN builders.
    users = [
        # DC — Document Controller
        ("D", "DC", OR,        "Hector Salazar"),
        ("D", "DC", DC,        "Karen Tan"),
        ("D", "DC", "dc_alt",  "Raj Kumar"),

        # SE — Senior Engineer
        ("D", "SE", SE,        "Nick Lim"),
        ("D", "SE", "se_user2","Aisha Mohd"),
        ("D", "SE", "se_user3","Wei Lin"),

        # CE — Chief Engineer
        ("D", "CE", CE,        "Branko Petrovic"),
        ("D", "CE", "ce_user2","Sandra Wong"),
        ("D", "CE", "ce_user3","Dinesh Nair"),

        # EM — Engineering Manager
        ("D", "EM", EM,        "Karen Chen"),
        ("D", "EM", "em_user2","Thomas Ng"),
        ("D", "EM", "em_user3","Priya Rajan"),

        # QM — Quality Manager
        ("D", "QM", QM,        "Divya Sharma"),
        ("D", "QM", "qm_user2","Lee Mei Ling"),
        ("D", "QM", "qm_user3","Ahmad Fadzil"),

        # PM — Production Manager
        ("D", "PM", PM,        "Jason Teo"),
        ("D", "PM", "pm_user2","Siti Rahimah"),
        ("D", "PM", "pm_user3","Lim Boon Keat"),

        # SC — Supply Chain / Purchasing
        ("D", "SC", SC,        "Michelle Tan"),
        ("D", "SC", "sc_user2","Farid Hassan"),
        ("D", "SC", "sc_user3","Chloe Yap"),

        # FN — Finance
        ("D", "FN", FN,        "Grace Lau"),
        ("D", "FN", "fn_user2","Azlan Ibrahim"),
        ("D", "FN", "fn_user3","Cindy Ho"),

        # CA — Cost Accountant (observer-plus)
        ("D", "CA", "ca_user", "Bernard Ong"),
        ("D", "CA", "ca_user2","Nurul Ain"),
        ("D", "CA", "ca_user3","Steven Koh"),

        # AD — Administrator
        ("D", "AD", OR,        "Hector Salazar"),
        ("D", "AD", DC,        "Karen Tan"),
        ("D", "AD", "ad_user", "Manal Al-Rashid"),

        # RD — R&D / Product Engineering (observer)
        ("D", "RD", "rd_user", "Victor Tan"),
        ("D", "RD", "rd_user2","Alicia Foo"),
        ("D", "RD", "rd_user3","Hafiz Zulkifli"),

        # TE — Test Engineering (observer)
        ("D", "TE", "te_user", "Marcus Yee"),
        ("D", "TE", "te_user2","Jasmine Loh"),
        ("D", "TE", "te_user3","Ravi Subramaniam"),

        # MQ — Manufacturing Quality (observer)
        ("D", "MQ", "mq_user", "Jenny Chai"),
        ("D", "MQ", "mq_user2","Zulhilmi Aris"),
        ("D", "MQ", "mq_user3","Patricia Yong"),
    ]

    # Mirror facility L (Johor Bahru) with same dev personas
    l_users = [("L", r, u, n) for _, r, u, n in users]

    for facility, role_id, username, display_name in users + l_users:
        email = f"{username}@srxglobal.local"
        await session.execute(
            sa.text(
                "INSERT INTO system_role_users "
                "(facility, role_id, username, display_name, email, is_active, added_by) "
                "VALUES (:facility, :role_id, :username, :display_name, :email, TRUE, 'seed_demo.py')"
            ),
            {"facility": facility, "role_id": role_id, "username": username,
             "display_name": display_name, "email": email},
        )


def _req(**kw) -> ECNCreateRequest:
    defaults = dict(
        facility="D", is_new_item=False, routing_changes=False,
        operation_changes=False, new_parts=False, lead_time_changes=False,
        change_to_documents=False, requires_customer_approval=False,
        regulatory_impact=False,
    )
    return ECNCreateRequest(**(defaults | kw))


async def _approve_all_steps(svc: ECNService, ecn_id: str) -> None:
    """Approve all pending management review steps using the assigned actor."""
    steps_result = await svc._session.execute(
        sa.text(
            "SELECT role_id, username FROM ecn_approval_steps "
            "WHERE ecn_id = :id AND at_status = 40 AND status = 'pending' AND skipped = FALSE"
        ),
        {"id": ecn_id},
    )
    steps = list(steps_result)
    for role_id, username in steps:
        actor = username or SE  # fall back to SE if not assigned
        await svc.approve_role(ecn_id, actor_username=actor, actor_role=role_id)


async def _advance(svc: ECNService, ecn_id: str, trigger: str,
                   actor: str, role: str, erp: MovexRestAdapter | None = None, **kw) -> None:
    req = ECNStatusTransitionRequest(trigger=trigger, actor_role=role, **kw)
    await svc.transition(ecn_id, req, actor_username=actor, erp=erp)


# ---------------------------------------------------------------------------
# ECN builders
# ---------------------------------------------------------------------------

async def _ecn_draft(svc: ECNService) -> str:
    ecn = await svc.create(
        _req(
            title="[DEMO] SMT line capacitor substitution",
            description=(
                "Replace C0402 100nF X5R 10V capacitors on PCBA-LF-001 with "
                "equivalent GRM155R61A104KA01 (Murata). Original part EOL Q3 2026. "
                "No electrical impact — same capacitance, voltage, temperature range."
            ),
            new_parts=True, lead_time_changes=True,
        ),
        OR,
    )
    await svc.create_item(ecn.id, line_number=10, item_number="LF-CAP-0100",
                          item_name="Cap 100nF 0402 X5R 10V", is_new_item=False)
    await svc.create_mpn(ecn.id, (await svc.list_items(ecn.id))[0].id,
                         mpn="GRM155R61A104KA01D", manufacturer="Murata", is_default=True)
    await svc.create_item(ecn.id, line_number=20, item_number="LF-CAP-0101",
                          item_name="Cap 47nF 0402 X7R 16V", is_new_item=False)
    # Real Movex items for the bulk routing/MPN upload demo (2026-07-21 weekly
    # meeting) — same LFAM050001 used in last week's live Movex write demo
    # (ECN-2026-D-0010) and same LM741CN/NOPB MPN used in last week's Autofill
    # demo. Existing items (is_new_item=False) so bulk upload can target them
    # without creating anything — see ai/tasks/demo-files/*.csv.
    await svc.create_item(ecn.id, line_number=30, item_number="LFAM050001",
                          item_name="SOLSHARE 35A PACKAGED UNIT", is_new_item=False)
    await svc.create_item(ecn.id, line_number=40, item_number="LFDR410018",
                          item_name="IC OPAMP GP 1 CIRCUIT 8SOIC", is_new_item=False)
    await svc.create_item(ecn.id, line_number=50, item_number="LFDR120001",
                          item_name="RES 1K OHM 1% 1/10W 0603", is_new_item=False)
    return ecn.id


async def _ecn_eng_review(svc: ECNService) -> str:
    ecn = await svc.create(
        _req(
            title="[DEMO] Replace connector J4 on PCB-A-001",
            description=(
                "Molex 53261 series connector (J4) has been discontinued. "
                "Replacing with Wurth 61900311121 — footprint-compatible, "
                "same pin count and contact rating."
            ),
            change_to_documents=True,
        ),
        OR,
    )
    item = await svc.create_item(ecn.id, line_number=10, item_number="LF-CON-0044",
                                 item_name="Connector 3-pin JST PH", is_new_item=False)
    await svc.create_mpn(ecn.id, item.id, mpn="61900311121",
                         manufacturer="Wurth Elektronik", is_default=True)
    await svc.create_mpn(ecn.id, item.id, mpn="53261-0371",
                         manufacturer="Molex", is_default=False)
    await _advance(svc, ecn.id, "submit", OR, "OR")
    return ecn.id


async def _ecn_mgmt_review(svc: ECNService) -> str:
    ecn = await svc.create(
        _req(
            title="[DEMO] New IC — LM2596 buck converter",
            description=(
                "Introducing LM2596 step-down DC/DC converter on PCBA-LF-003 "
                "to replace linear regulator LM7805. Reduces heat dissipation by ~60%. "
                "New layout required — drawing number to be assigned by DC."
            ),
            is_new_item=True, routing_changes=True,
        ),
        OR,
    )
    item = await svc.create_item(ecn.id, line_number=10, item_number="LF-IC-0220",
                                 item_name="IC Buck Conv LM2596 TO-263", is_new_item=True)
    await svc.create_mpn(ecn.id, item.id, mpn="LM2596S-5.0/NOPB",
                         manufacturer="Texas Instruments", is_default=True)
    await svc.create_routing_operation(
        ecn.id, item.id,
        RoutingOperationRequest(
            operation_number=10, operation_description="SMT placement — DC/DC area",
            work_centre="SMT01", run_time=45.0, setup_time=15.0, change_type="ADD",
        ),
    )
    await _advance(svc, ecn.id, "submit", OR, "OR")
    await _advance(svc, ecn.id, "approve_engineering", SE, "SE")
    return ecn.id


async def _ecn_dc_approved(svc: ECNService) -> str:
    ecn = await svc.create(
        _req(
            title="[DEMO] Routing change — remove wave solder op",
            description=(
                "Wave solder operation (op 30) on PCBA-LF-007 is redundant following "
                "conversion to full SMT. Removing to reduce cycle time by 8 min/board."
            ),
            routing_changes=True, operation_changes=True,
        ),
        OR,
    )
    item = await svc.create_item(ecn.id, line_number=10, item_number="LF-PCBA-007",
                                 item_name="PCBA Power Supply LF-007")
    await svc.create_routing_operation(
        ecn.id, item.id,
        RoutingOperationRequest(
            operation_number=30, operation_description="Wave solder",
            work_centre="WAVE01", run_time=480.0, setup_time=60.0, change_type="DELETE",
        ),
    )
    await _advance(svc, ecn.id, "submit", OR, "OR")
    await _advance(svc, ecn.id, "approve_engineering", SE, "SE")
    await _approve_all_steps(svc, ecn.id)
    return ecn.id


async def _ecn_approved(svc: ECNService) -> str:
    ecn = await svc.create(
        _req(
            title="[DEMO] BOM rationalisation — Q2 2026",
            description=(
                "Consolidate three similar 10kΩ 0402 resistors to a single preferred "
                "part number (Yageo RC0402FR-0710KL) across all JB facility PCBAs. "
                "No functional change — pure procurement rationalisation."
            ),
            new_parts=True,
        ),
        OR,
    )
    item = await svc.create_item(ecn.id, line_number=10, item_number="LF-RES-0010",
                                 item_name="Res 10k 0402 1% 62.5mW")
    await svc.create_mpn(ecn.id, item.id, mpn="RC0402FR-0710KL",
                         manufacturer="Yageo", is_default=True)
    await svc.create_item(ecn.id, line_number=20, item_number="LF-RES-0011",
                          item_name="Res 10k 0402 1% 63mW supsd")
    await svc.create_item(ecn.id, line_number=30, item_number="LF-RES-0012",
                          item_name="Res 10k 0402 1% 100mW supsd")
    await _advance(svc, ecn.id, "submit", OR, "OR")
    await _advance(svc, ecn.id, "approve_engineering", SE, "SE")
    await _approve_all_steps(svc, ecn.id)
    await _advance(svc, ecn.id, "dc_approve", DC, "DC")
    return ecn.id


async def _ecn_rejected(svc: ECNService) -> str:
    ecn = await svc.create(
        _req(
            title="[DEMO] Add conformal coating step — PCBA-LF-002",
            description=(
                "Add IPC-CC-830 compliant conformal coating to PCBA-LF-002 boards "
                "destined for outdoor enclosure units. Coating: Humiseal 1A33."
            ),
            routing_changes=True,
        ),
        OR,
    )
    item = await svc.create_item(ecn.id, line_number=10, item_number="LF-PCBA-002",
                                 item_name="PCBA Motor Control LF-002")
    await svc.create_routing_operation(
        ecn.id, item.id,
        RoutingOperationRequest(
            operation_number=90, operation_description="Conformal coat Humiseal 1A33",
            work_centre="COAT01", run_time=600.0, setup_time=120.0, change_type="ADD",
        ),
    )
    await _advance(svc, ecn.id, "submit", OR, "OR")
    await _advance(
        svc, ecn.id, "reject", SE, "SE",
        rejection_reason=(
            "IPC-CC-830 certification for Humiseal 1A33 has not been verified for "
            "this substrate. Please obtain coating compatibility report from supplier "
            "and resubmit with supporting documentation attached."
        ),
    )
    return ecn.id


async def _ecn_on_hold(svc: ECNService) -> str:
    """ON_HOLD (90) — paused mid-review by the DC.

    The only status the demo set otherwise never reaches, so nothing exercised
    the hold banner, the resume action, or the pre-hold status badge. Held from
    MANAGEMENT_REVIEW because that is where a real hold usually happens: an
    approver asks a question the originator cannot answer immediately.

    `place_on_hold` requires BOTH a reason and an expected resume date — the
    guard rejects the transition without them.
    """
    ecn = await svc.create(
        _req(
            title="[DEMO] Supplier change — TDK to Murata inductors",
            description=(
                "Second-source the 10uH power inductor on PCBA-LF-004 from Murata "
                "following extended TDK lead times. Electrically equivalent; "
                "footprint identical."
            ),
            new_parts=True, lead_time_changes=True,
        ),
        OR,
    )
    item = await svc.create_item(ecn.id, line_number=10, item_number="LF-IND-0010",
                                 item_name="Inductor 10uH 20% 1210", is_new_item=True)
    await svc.create_mpn(ecn.id, item.id, mpn="DFE252012F-100M",
                         manufacturer="Murata", is_default=True)
    await _advance(svc, ecn.id, "submit", OR, "OR")
    await _advance(svc, ecn.id, "approve_engineering", SE, "SE")
    await _advance(
        svc, ecn.id, "place_on_hold", DC, "DC",
        hold_reason=(
            "Awaiting qualification test report from Murata. Quality will not "
            "approve the second source until DCR and saturation-current data "
            "for the new part are on file."
        ),
        expected_resume_date=(date.today() + timedelta(days=21)).isoformat(),
    )
    return ecn.id


async def _ecn_closed(svc: ECNService) -> str:
    ecn = await svc.create(
        _req(
            title="[DEMO] Phase 1 EOL component swap — LF-005 series",
            description=(
                "Systematic replacement of all Vishay CRCW0402 resistors with "
                "Yageo RC series equivalents following Vishay EOL notice Q4 2025. "
                "Affects 12 part numbers across LF-005 product family."
            ),
            new_parts=True, lead_time_changes=True,
        ),
        OR,
    )
    await svc.create_item(ecn.id, line_number=10, item_number="LF-RES-0050",
                          item_name="Res 100R 0402 1% Yageo")
    await svc.create_item(ecn.id, line_number=20, item_number="LF-RES-0051",
                          item_name="Res 470R 0402 1% Yageo")
    await _advance(svc, ecn.id, "submit", OR, "OR")
    await _advance(svc, ecn.id, "approve_engineering", SE, "SE")
    await _approve_all_steps(svc, ecn.id)
    await _advance(svc, ecn.id, "dc_approve", DC, "DC")
    # dc_approve auto-advances straight to IMPLEMENTED when nothing gets
    # queued to movex_outbox (no routing/BOM changes here) — workflow.py's
    # transition() fires movex_write_complete itself in that case, so calling
    # it again here would be an invalid transition. Only call it explicitly
    # if dc_approve didn't already do so.
    current = await svc.get(ecn.id)
    if current.status_name == "DC_APPROVED":
        await _advance(svc, ecn.id, "movex_write_complete", OR, "OR")
    await _advance(svc, ecn.id, "auto_close", OR, "OR")
    return ecn.id


# ---------------------------------------------------------------------------
# BOM module builders (Slice E, I2-6) — all target LF100001, the item
# tests/fixtures/bom/single_level.json and scripts/movex_stub.py both serve
# (12 lines: LF200010..LF200020, see the fixture for the full live shape).
# ---------------------------------------------------------------------------

_BOM_ITEM = "LF100001"


async def _ecn_bom_draft(svc: ECNService) -> str:
    """DRAFT with one ADD, one CHANGE, and one DELETE bom_changes row — shows
    BOMChangesPanel populated with all three change types before any workflow
    transition, no ERP call needed (create_bom_change is pure DB CRUD)."""
    ecn = await svc.create(
        _req(
            title="[DEMO] BOM changes — Widget Assembly A rev",
            description=(
                "Rev change on Widget Assembly A (LF100001): add a new bypass "
                "capacitor at op 10, swap the MCU for a pin-compatible variant "
                "with higher flash, and remove the now-redundant status LED."
            ),
            new_parts=True,
        ),
        OR,
    )
    item = await svc.create_item(ecn.id, line_number=10, item_number=_BOM_ITEM,
                                 item_name="Widget Assembly A", is_new_item=False)
    await svc.create_bom_change(
        ecn.id, item.id,
        BOMChangeRequest(
            change_type="ADD", component_number="LF200021",
            quantity=1.0, unit_of_measure="EA", operation_number=10,
            from_date=20260901,
            notes="New bypass cap — added per SI review, see attached sim results.",
        ),
    )
    await svc.create_bom_change(
        ecn.id, item.id,
        BOMChangeRequest(
            change_type="CHANGE", component_number="LF200012",
            quantity=1.0, unit_of_measure="EA", operation_number=10,
            from_date=20260901, old_from_date=20240101, old_quantity=1.0,
            notes="STM32F103 -> STM32F103 (256K flash variant), pin-compatible.",
        ),
    )
    await svc.create_bom_change(
        ecn.id, item.id,
        BOMChangeRequest(
            change_type="DELETE", component_number="LF200015",
            operation_number=20, old_from_date=20240101,
            notes="Status LED removed — superseded by host-side status reporting.",
        ),
    )
    return ecn.id


async def _ecn_bom_dc_approved(svc: ECNService, erp: MovexRestAdapter | None) -> str:
    """Carries one ADD + one CHANGE through submit -> dc_approve so, when erp
    is reachable, this ECN has gone through a real submit-time snapshot
    capture and dc_approve concurrency re-fetch, and _queue_bom_changes_outbox
    has queued real movex_outbox rows (AddComponent for the ADD; an
    UpdateComponent close row + a depends_on-linked AddComponent add row for
    the CHANGE, per D6's supersession model)."""
    ecn = await svc.create(
        _req(
            title="[DEMO] BOM supersession — connector swap",
            description=(
                "Widget Assembly A (LF100001): add a new fixed-mount connector "
                "and supersede the existing 4-pin JST with a locking variant "
                "to prevent field disconnection. Approved by DC 2026-08-11."
            ),
        ),
        OR,
    )
    item = await svc.create_item(ecn.id, line_number=10, item_number=_BOM_ITEM,
                                 item_name="Widget Assembly A", is_new_item=False)
    await svc.create_bom_change(
        ecn.id, item.id,
        BOMChangeRequest(
            change_type="ADD", component_number="LF200022",
            quantity=1.0, unit_of_measure="EA", operation_number=20,
            from_date=20260901,
            notes="Fixed-mount bracket connector — new requirement from field team.",
        ),
    )
    await svc.create_bom_change(
        ecn.id, item.id,
        BOMChangeRequest(
            change_type="CHANGE", component_number="LF200013",
            quantity=2.0, unit_of_measure="EA", operation_number=20,
            from_date=20260901, old_from_date=20240101, old_quantity=2.0,
            notes="4-pin JST -> 4-pin JST locking variant (field disconnect fix).",
        ),
    )
    await _advance(svc, ecn.id, "submit", OR, "OR", erp=erp)
    await _advance(svc, ecn.id, "approve_engineering", SE, "SE")
    await _approve_all_steps(svc, ecn.id)
    await _advance(svc, ecn.id, "dc_approve", DC, "DC", erp=erp)
    return ecn.id


async def _ecn_bom_conflict(svc: ECNService, stub_client: httpx.AsyncClient | None) -> str | None:
    """Submits with a CHANGE on LF200011, mutates the stub's live BOM on that
    exact key between submit and dc_approve (via /_test-mutate), then attempts
    dc_approve — the concurrency gate must catch the conflict and raise, so
    the ECN stays at MANAGEMENT_REVIEW rather than advancing. Requires the
    stub specifically (real movex-rest-api has no /_test-mutate endpoint) —
    returns None (skipped) if stub_client is None."""
    if stub_client is None:
        return None

    ecn = await svc.create(
        _req(
            title="[DEMO] BOM change blocked by live conflict",
            description=(
                "Widget Assembly A (LF100001): change the 100nF bypass "
                "capacitor's value. Demonstrates the dc_approve concurrency "
                "gate — the live BOM was edited by someone else after this "
                "ECN was submitted, on the exact line this ECN is changing, "
                "so dc_approve is blocked until the conflict is resolved."
            ),
        ),
        OR,
    )
    item = await svc.create_item(ecn.id, line_number=10, item_number=_BOM_ITEM,
                                 item_name="Widget Assembly A", is_new_item=False)
    await svc.create_bom_change(
        ecn.id, item.id,
        BOMChangeRequest(
            change_type="CHANGE", component_number="LF200011",
            quantity=10.0, unit_of_measure="EA", operation_number=10,
            from_date=20260901, old_from_date=20240101, old_quantity=8.0,
            notes="100nF -> 100nF x10 array, per updated decoupling analysis.",
        ),
    )
    erp = MovexRestAdapter()
    await erp.open()
    try:
        await _advance(svc, ecn.id, "submit", OR, "OR", erp=erp)
        await _advance(svc, ecn.id, "approve_engineering", SE, "SE")
        await _approve_all_steps(svc, ecn.id)

        # Simulate someone else editing the live BOM on the same key
        # (LF200011 @ op 10) after this ECN's submit-time snapshot was taken.
        # Payload shape matches ecn-bom-changes.spec.ts: fetch the current
        # BOM, mutate the matching line, POST the full {data:{head,records}}
        # body back — /_test-mutate replaces the whole GET response, it does
        # not accept a field-level patch.
        current = (await stub_client.get(f"/api/bom/{_BOM_ITEM}")).json()
        mutated = {
            "data": {
                "head": current["data"]["head"],
                "records": [
                    {**r, "CNQT": 10.0}
                    if r["MTNO"] == "LF200011" and r["OPNO"] == 10
                    else r
                    for r in current["data"]["records"]
                ],
            },
        }
        await stub_client.post(f"/_test-mutate/bom/{_BOM_ITEM}", json=mutated)

        try:
            await _advance(svc, ecn.id, "dc_approve", DC, "DC", erp=erp)
        except Exception:
            pass  # expected — concurrency gate should block this
        finally:
            await stub_client.post(f"/_test-mutate/bom/{_BOM_ITEM}/reset")
    finally:
        await erp.close()
    return ecn.id


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    print("OSKAR Demo Seed")
    print(f"  DB: {_DB_URL.split('@')[-1]}")

    engine = create_async_engine(_DB_URL, echo=False, pool_size=2)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False,
                                 autoflush=False, autocommit=False)

    async with factory() as session:
        async with session.begin():
            wiped = await _wipe_demo_ecns(session)
            await _ensure_role_users(session)
        print(f"  Wiped {wiped} existing [DEMO] ECN(s)")

    builders = [
        ("DRAFT",              _ecn_draft),
        ("ENGINEERING_REVIEW", _ecn_eng_review),
        ("MANAGEMENT_REVIEW",  _ecn_mgmt_review),
        ("DC_APPROVED",        _ecn_dc_approved),
        ("APPROVED",           _ecn_approved),
        ("REJECTED",           _ecn_rejected),
        ("ON_HOLD",            _ecn_on_hold),
        ("CLOSED",             _ecn_closed),
    ]

    for label, builder in builders:
        async with factory() as session:
            async with session.begin():
                svc = ECNService(session)
                try:
                    ecn_id = await builder(svc)
                    ecn = await svc.get(ecn_id)
                    print(f"  ✓  {label:<22} {ecn.ecn_number}  —  {ecn.title[7:42]}...")
                except Exception as exc:
                    print(f"  ✗  {label:<22} FAILED: {exc}")
                    raise

    # ── BOM module demo ECNs (Slice E) ──────────────────────────────────────
    # Probe MOVEX_API_URL once — reachable means we can exercise a real
    # snapshot/concurrency-gate cycle; unreachable means those ECNs still get
    # created (with their bom_changes rows) but skip the ERP-touching steps,
    # same as production's own degrade-gracefully behaviour. Only the stub
    # exposes /_test-mutate, so the conflict ECN additionally checks that
    # MOVEX_API_URL actually points at a stub instance (not the real API)
    # before attempting it.
    erp = MovexRestAdapter()
    await erp.open()

    # health_check() hits /health, which scripts/movex_stub.py doesn't
    # implement (it's a fixture-serving stub, not a full API surface) — so it
    # would always report the stub as unreachable even when it's up and
    # serving BOM data fine. Probe the actual B-1 route both adapters serve
    # instead: it exists on the real API and the stub alike, so a 200 here
    # means "can fetch LF100001's BOM," which is genuinely what these demo
    # ECNs need, regardless of whether /health exists.
    try:
        # erp._http's base_url already includes the /api suffix from
        # MOVEX_API_URL — same convention every real adapter method uses
        # (e.g. get_bom's self._get(f"/bom/{item_number}", ...)).
        probe = await erp._http.get(f"/bom/{_BOM_ITEM}")
        erp_reachable = probe.status_code == 200
    except Exception:
        erp_reachable = False

    # _test-mutate lives OUTSIDE /api (see scripts/movex_stub.py's route
    # decorators) — needs the bare host root, not erp.base_url.
    _stub_root = erp.base_url.removesuffix("/api")

    # Probe for /_test-mutate directly rather than guessing stub-vs-real from
    # the URL/port — the real movex-rest-api returns 404/405 here since the
    # route doesn't exist at all; the stub always returns 200.
    is_stub = False
    if erp_reachable:
        try:
            async with httpx.AsyncClient(base_url=_stub_root, timeout=5.0) as probe_client:
                probe = await probe_client.post(f"/_test-mutate/bom/{_BOM_ITEM}/reset")
                is_stub = probe.status_code == 200
        except Exception:
            is_stub = False

    if not erp_reachable:
        print(f"\n  MOVEX_API_URL ({erp.base_url}) unreachable — BOM ECNs 9-10 will "
              f"skip snapshot/concurrency-gate steps (see 'BOM demo notes' in this "
              f"script's docstring to run scripts/movex_stub.py first).")

    async with factory() as session:
        async with session.begin():
            svc = ECNService(session)
            try:
                ecn_id = await _ecn_bom_draft(svc)
                ecn = await svc.get(ecn_id)
                print(f"  ✓  {'DRAFT (BOM)':<22} {ecn.ecn_number}  —  {ecn.title[7:42]}...")
            except Exception as exc:
                print(f"  ✗  {'DRAFT (BOM)':<22} FAILED: {exc}")
                raise

    async with factory() as session:
        async with session.begin():
            svc = ECNService(session)
            try:
                ecn_id = await _ecn_bom_dc_approved(svc, erp if erp_reachable else None)
                ecn = await svc.get(ecn_id)
                print(f"  ✓  {'DC_APPROVED (BOM)':<22} {ecn.ecn_number}  —  {ecn.title[7:42]}...")
            except Exception as exc:
                print(f"  ✗  {'DC_APPROVED (BOM)':<22} FAILED: {exc}")
                raise

    if is_stub:
        async with httpx.AsyncClient(base_url=_stub_root, timeout=10.0) as stub_client:
            async with factory() as session:
                async with session.begin():
                    svc = ECNService(session)
                    try:
                        ecn_id = await _ecn_bom_conflict(svc, stub_client)
                        ecn = await svc.get(ecn_id)
                        print(f"  ✓  {'DC_APPROVED (blocked)':<22} {ecn.ecn_number}  —  {ecn.title[7:42]}...")
                    except Exception as exc:
                        print(f"  ✗  {'DC_APPROVED (blocked)':<22} FAILED: {exc}")
                        raise
    else:
        print(f"  ⊘  {'DC_APPROVED (blocked)':<22} skipped — needs scripts/movex_stub.py "
              f"specifically (real movex-rest-api has no /_test-mutate endpoint)")

    await erp.close()
    await engine.dispose()
    print("\nDone. Open http://localhost:5173 and log in as hsalazar / eng_user / dc_user.")


if __name__ == "__main__":
    asyncio.run(main())
