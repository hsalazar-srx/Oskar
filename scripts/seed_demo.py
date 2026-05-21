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
1. DRAFT          — "SMT line capacitor substitution"         (hsalazar)
2. ENGINEERING_REVIEW — "Replace connector J4 on PCB-A-001"  (hsalazar, submitted)
3. MANAGEMENT_REVIEW  — "New IC — LM2596 buck converter"      (hsalazar, SE approved)
4. DC_APPROVED    — "Routing change — remove wave solder op"   (hsalazar, full approval)
5. APPROVED       — "BOM rationalisation — Q2 2026"            (hsalazar, DC approved)
6. REJECTED       — "Add conformal coating step"               (eng_user, rejected by SE)
7. CLOSED         — "Phase 1 EOL component swap"               (hsalazar, archived)

Each ECN has:
  - 1–3 line items with realistic part numbers and descriptions
  - MPNs with manufacturer references where relevant
  - Routing operations (where routing_changes=True)
  - Full audit chain (real transitions via ECNService — not raw SQL)

Idempotent: deletes existing demo ECNs by title prefix "[DEMO]" before re-creating.
Safe to run against dev DB. Never touches the test DB (port 5433).

Demo personas (all in DEV_USERS, no LDAP needed):
  hsalazar  — Originator / DC
  eng_user  — Senior Engineer (SE)
  qm_user   — Quality Manager (QM)
  dc_user   — Document Controller (DC)
"""
from __future__ import annotations

import asyncio
import os
import sys

# Allow running from project root inside Docker (/app) or Windows host
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.services.ecn.models import (
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
# Personas
# ---------------------------------------------------------------------------

OR = "hsalazar"       # Originator / also DC for demo simplicity
SE = "eng_user"       # Senior Engineer
QM = "qm_user"        # Quality Manager
DC = "dc_user"        # Document Controller


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
        # routing_operations and mpns hang off ecn_items, not ecn_id directly
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
        for tbl in (
            "ecn_transition_history",
            "ecn_rejections",
            "ecn_approval_steps",
            "ecn_role_assignments",
            "ecn_items",
            "movex_outbox",
        ):
            await session.execute(
                sa.text(f"DELETE FROM {tbl} WHERE ecn_id = :id"), {"id": ecn_id}
            )
        await session.execute(
            sa.text("DELETE FROM ecn_instances WHERE id = :id"), {"id": ecn_id}
        )
    return len(ids)


async def _ensure_role_users(session: AsyncSession) -> None:
    """Set exactly one user per role for facility L.

    _auto_assign_roles sets username=None when multiple users share a role,
    which violates the NOT NULL constraint. We clear and rebuild with one
    canonical persona per role so auto-assignment always resolves.
    """
    # Remove all existing facility L role users and start clean
    await session.execute(
        sa.text("DELETE FROM system_role_users WHERE facility = 'L'")
    )

    # One canonical user per role — roles that map to the same person are fine
    users = [
        ("L", "DC", DC,  "Doc Controller",    f"{DC}@srxglobal.local"),
        ("L", "SE", SE,  "Engineering User",  f"{SE}@srxglobal.local"),
        ("L", "QM", QM,  "Quality Manager",   f"{QM}@srxglobal.local"),
        ("L", "EM", SE,  "Engineering User",  f"{SE}@srxglobal.local"),
        ("L", "PM", QM,  "Quality Manager",   f"{QM}@srxglobal.local"),
        ("L", "SC", QM,  "Quality Manager",   f"{QM}@srxglobal.local"),
        ("L", "FN", QM,  "Quality Manager",   f"{QM}@srxglobal.local"),
        ("L", "AD", OR,  "Hector Salazar",    f"{OR}@srxglobal.local"),
        ("L", "CE", SE,  "Engineering User",  f"{SE}@srxglobal.local"),
        ("L", "RD", SE,  "Engineering User",  f"{SE}@srxglobal.local"),
        ("L", "TE", SE,  "Engineering User",  f"{SE}@srxglobal.local"),
        ("L", "MQ", QM,  "Quality Manager",   f"{QM}@srxglobal.local"),
        ("L", "CA", DC,  "Doc Controller",    f"{DC}@srxglobal.local"),
    ]
    for facility, role_id, username, display_name, email in users:
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
        facility="L", is_new_item=False, routing_changes=False,
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
                   actor: str, role: str, **kw) -> None:
    req = ECNStatusTransitionRequest(trigger=trigger, actor_role=role, **kw)
    await svc.transition(ecn_id, req, actor_username=actor)


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
    await _advance(svc, ecn.id, "movex_write_complete", OR, "OR")
    await _advance(svc, ecn.id, "auto_close", OR, "OR")
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

    await engine.dispose()
    print("\nDone. Open http://localhost:5173 and log in as hsalazar / eng_user / dc_user.")


if __name__ == "__main__":
    asyncio.run(main())
