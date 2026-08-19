#!/usr/bin/env python
"""
OSKAR — pre-UAT preflight check (robustness plan §7).

What this is
------------
The concrete, repeatable answer to "did we actually check this works today?"
Run it before each UAT milestone. It is deliberately NOT part of CI: several
checks write to real M3 (CONO=300) and one spends real DigiKey quota.

Every check verifies a REAL boundary, not a mock. That is the whole point —
the two bugs that prompted this plan (I2-19, I2-21) both passed a full mocked
suite for weeks while silently doing nothing.

Checks
------
  1. Movex write path      — read/add/read-back/delete/read-back round trip
                             against real M3, asserting via fresh reads
  2. Celery worker         — a real worker is consuming from the Postgres broker
  3. Crash recovery        — the stale-'processing' sweeper is scheduled AND
                             registered (an unscheduled sweeper fixes nothing)
  4. Email deliverability  — mail is accepted by a real SMTP server with correct
                             headers (Mailpit; never the production relay)
  5. ECN happy path        — approved ECN's ordered writes reach M3 via the
                             real worker (routing-before-BOM, S-3)
  6. ECN rejection path    — a rejected ECN writes NOTHING to M3
  7. DigiKey               — live API auth + response-shape drift (quota-aware)

Usage
-----
    python scripts/preflight_check.py              # everything except DigiKey
    python scripts/preflight_check.py --with-digikey
    python scripts/preflight_check.py --only movex,worker

DigiKey is opt-in because it spends from a 1000/month budget. Everything else
is free to run as often as useful.

Exit codes: 0 = all checks passed, 1 = one or more failed/skipped-with-cause.
A SKIP (missing prerequisite, e.g. Mailpit not running) is reported distinctly
from a FAIL and does NOT count as a pass — silence must never look like success.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from typing import Any, Callable

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


class Result:
    def __init__(self, name: str, status: str, detail: str = "", seconds: float = 0.0):
        self.name, self.status, self.detail, self.seconds = name, status, detail, seconds


def _run_script(script: str, *args: str, timeout: int = 600) -> tuple[int, str]:
    """Run a sibling script in-process-isolated; return (exit_code, tail)."""
    proc = subprocess.run(
        [sys.executable, os.path.join(REPO, "scripts", script), *args],
        capture_output=True, text=True, timeout=timeout, cwd=REPO,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    tail = "\n".join(
        ln for ln in out.splitlines()
        if ln.strip() and not ln.startswith("20")  # drop structlog lines
    )[-1200:]
    return proc.returncode, tail


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

# Signatures of M3/AS-400 being unreachable, as opposed to Oskar misbehaving.
# CWBCO1004 is the IBM i Access ODBC driver failing to resolve the host; the
# 502 is movex-rest-api surfacing that. Distinguishing these matters: an
# infrastructure outage reported as a code FAIL sends someone debugging the
# wrong thing, and (worse) a checklist that cries wolf gets ignored.
_M3_DOWN_MARKERS = (
    "CWBCO1004",
    "Communication link failure",
    "502 Bad Gateway",
    "circuit breaker is open",
)


def _is_m3_unreachable(text: str) -> bool:
    return any(m in text for m in _M3_DOWN_MARKERS)


def check_movex() -> Result:
    code, tail = _run_script("movex_smoke_test.py", timeout=420)
    if code == 0:
        return Result("Movex write path", PASS, "round trip verified against real M3")
    if code == 2:
        return Result("Movex write path", SKIP, "refused — unsafe config (check MOVEX_CONO)")
    if _is_m3_unreachable(tail):
        return Result("Movex write path", SKIP,
                      "M3/AS-400 unreachable (CWBCO1004 / 502) — infrastructure, "
                      "not an Oskar regression; boundary left UNVERIFIED")
    last = [l for l in tail.splitlines() if "FAIL" in l or "RESULT" in l]
    return Result("Movex write path", FAIL, last[-1] if last else tail[-200:])


def check_worker() -> Result:
    """A real worker must be consuming from the broker.

    Deliberately not `celery inspect ping` — that rides a broadcast mailbox
    Kombu's SQLAlchemy transport does not implement, so it returns empty even
    when the worker is healthy (verified 2026-08-17: a worker reported
    'unhealthy' for 3 days while processing tasks normally). Liveness is
    proven by enqueueing a real task and watching it get consumed.
    """
    try:
        import psycopg2
        from celery import Celery
    except Exception as exc:
        return Result("Celery worker", SKIP, f"import failed: {exc}")

    dsn = os.environ.get(
        "DATABASE_URL", "postgresql://oskar:oskar_dev@oskar-test-db:5432/oskar_test"
    ).replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg2://", "postgresql://").split("?")[0]
    sync = dsn.replace("postgresql://", "postgresql+psycopg2://")

    try:
        conn = psycopg2.connect(dsn, connect_timeout=5)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.kombu_message')")
            if cur.fetchone()[0] is None:
                conn.close()
                return Result("Celery worker", SKIP,
                              "no kombu_message table — broker never used")
        conn.close()
    except Exception as exc:
        return Result("Celery worker", SKIP, f"cannot reach broker DB: {exc}")

    app = Celery("preflight")
    app.conf.update(broker_url=f"sqla+{sync}", result_backend=f"db+{sync}",
                    broker_connection_retry_on_startup=False)
    try:
        # A nonexistent outbox id: the task returns 'skipped:not_found' quickly
        # and harmlessly, while still proving a worker consumed and ran it.
        res = app.send_task("oskar.tasks.process_outbox_entry",
                            args=["00000000-0000-0000-0000-000000000000"])
        deadline = time.time() + 45
        while time.time() < deadline:
            if res.ready():
                return Result("Celery worker", PASS,
                              f"worker consumed task -> {res.result}")
            time.sleep(0.5)
        return Result("Celery worker", FAIL,
                      "no worker consumed the task within 45s — apply_async is a "
                      "silent no-op, so no Movex write would ever dispatch")
    except Exception as exc:
        return Result("Celery worker", FAIL, str(exc))


def check_crash_recovery() -> Result:
    """The sweeper must be BOTH registered and scheduled.

    A sweeper that exists but is not on the beat schedule fixes nothing — and
    would pass any unit test written against the function directly.
    """
    try:
        from src.tasks.celery_app import celery_app
        celery_app.loader.import_default_modules()
        registered = set(celery_app.tasks.keys())
        scheduled = {e["task"] for e in celery_app.conf.beat_schedule.values()}
        name = "oskar.tasks.sweep_stale_processing_entries"

        if name not in registered:
            return Result("Crash recovery", FAIL, f"{name} is not registered")
        if name not in scheduled:
            return Result("Crash recovery", FAIL,
                          f"{name} is registered but NOT on the beat schedule — "
                          f"stranded 'processing' rows would never be reclaimed")
        missing = [n for n, e in celery_app.conf.beat_schedule.items()
                   if e["task"] not in registered]
        if missing:
            return Result("Crash recovery", FAIL,
                          f"beat entries reference unregistered tasks: {missing}")
        return Result("Crash recovery", PASS,
                      f"sweeper scheduled; all {len(scheduled)} beat entries resolve")
    except Exception as exc:
        return Result("Crash recovery", FAIL, str(exc))


def check_email() -> Result:
    """Mail must be accepted by a real SMTP server with correct headers."""
    try:
        import asyncio
        import uuid as _uuid

        import httpx
    except Exception as exc:
        return Result("Email deliverability", SKIP, f"import failed: {exc}")

    api = os.environ.get("MAILPIT_API", "http://localhost:8025")
    host = os.environ.get("MAILPIT_SMTP_HOST", "localhost")
    port = int(os.environ.get("MAILPIT_SMTP_PORT", "1025"))

    try:
        httpx.get(f"{api}/api/v1/messages", timeout=3.0).raise_for_status()
    except Exception:
        return Result("Email deliverability", SKIP,
                      "Mailpit not reachable — start the 'mail' compose profile")

    token = f"preflight-{_uuid.uuid4().hex[:8]}"
    try:
        from src.tasks import ecn_notifications as en
        old_host, old_port = en._SMTP_HOST, en._SMTP_PORT
        en._SMTP_HOST, en._SMTP_PORT = host, port
        try:
            asyncio.run(en.ECNEmailService().send(
                to=["preflight@example.com"],
                subject=f"[OSKAR] {token} preflight",
                body_html="<p>preflight deliverability check</p>",
            ))
        finally:
            en._SMTP_HOST, en._SMTP_PORT = old_host, old_port

        deadline = time.time() + 15
        while time.time() < deadline:
            msgs = httpx.get(f"{api}/api/v1/messages", timeout=5.0).json().get("messages", [])
            hit = next((m for m in msgs if token in m.get("Subject", "")), None)
            if hit:
                detail = httpx.get(f"{api}/api/v1/message/{hit['ID']}", timeout=5.0).json()
                frm = (detail.get("From") or {}).get("Address", "")
                to = [t.get("Address", "") for t in (detail.get("To") or [])]
                if "preflight@example.com" not in to:
                    return Result("Email deliverability", FAIL,
                                  f"delivered to the wrong recipient: {to}")
                if not frm or "@" not in frm:
                    return Result("Email deliverability", FAIL,
                                  f"malformed From address: {frm!r}")
                return Result("Email deliverability", PASS,
                              f"delivered from {frm} to {to[0]}")
            time.sleep(0.5)
        return Result("Email deliverability", FAIL,
                      "message never arrived — SMTP reported success but nothing "
                      "was delivered")
    except Exception as exc:
        return Result("Email deliverability", FAIL, str(exc))


def check_happy_path() -> Result:
    code, tail = _run_script("e2e_s3_ordering_proof.py", timeout=600)
    if code == 0:
        return Result("ECN happy path (E2E)", PASS,
                      "ordered writes reached real M3 via the real worker")
    if code == 2:
        reason = next((l for l in tail.splitlines() if "FAIL" in l), "prerequisites not met")
        return Result("ECN happy path (E2E)", SKIP, reason[:160])
    if _is_m3_unreachable(tail):
        return Result("ECN happy path (E2E)", SKIP,
                      "M3/AS-400 unreachable — infrastructure, not an Oskar "
                      "regression; boundary left UNVERIFIED")
    last = [l for l in tail.splitlines() if "FAIL" in l]
    return Result("ECN happy path (E2E)", FAIL, last[-1][:200] if last else tail[-200:])


def check_rejection_path() -> Result:
    code, tail = _run_script("e2e_rejection_path.py", timeout=600)
    if code == 0:
        return Result("ECN rejection path (E2E)", PASS,
                      "rejected ECN wrote nothing; approved ECN wrote correctly")
    if code == 2:
        reason = next((l for l in tail.splitlines() if "FAIL" in l), "prerequisites not met")
        return Result("ECN rejection path (E2E)", SKIP, reason[:160])
    if _is_m3_unreachable(tail):
        return Result("ECN rejection path (E2E)", SKIP,
                      "M3/AS-400 unreachable — infrastructure, not an Oskar "
                      "regression; boundary left UNVERIFIED")
    last = [l for l in tail.splitlines() if "FAIL" in l]
    return Result("ECN rejection path (E2E)", FAIL, last[-1][:200] if last else tail[-200:])


def check_digikey() -> Result:
    if not os.environ.get("DIGIKEY_CLIENT_ID"):
        return Result("DigiKey (live)", SKIP, "DIGIKEY_CLIENT_ID not set")
    code, tail = _run_script("digikey_verify.py", timeout=300)
    used = next((l.strip() for l in tail.splitlines() if "API calls used" in l), "")
    if code == 0:
        return Result("DigiKey (live)", PASS, f"adapter matches live API ({used})")
    if code == 2:
        return Result("DigiKey (live)", SKIP, f"refused — {used}")
    last = [l for l in tail.splitlines() if "FAIL" in l]
    return Result("DigiKey (live)", FAIL, last[-1][:200] if last else tail[-200:])


CHECKS: dict[str, Callable[[], Result]] = {
    "movex": check_movex,
    "worker": check_worker,
    "crash": check_crash_recovery,
    "email": check_email,
    "happy": check_happy_path,
    "reject": check_rejection_path,
    "digikey": check_digikey,
}

DEFAULT_ORDER = ["movex", "worker", "crash", "email", "happy", "reject"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-digikey", action="store_true",
                        help="include the live DigiKey check (spends real quota)")
    parser.add_argument("--only", type=str, default="",
                        help=f"comma-separated subset of: {','.join(CHECKS)}")
    args = parser.parse_args()

    if args.only:
        names = [n.strip() for n in args.only.split(",") if n.strip()]
        unknown = [n for n in names if n not in CHECKS]
        if unknown:
            print(f"unknown check(s): {unknown}; valid: {list(CHECKS)}")
            return 1
    else:
        names = list(DEFAULT_ORDER)
        if args.with_digikey:
            names.append("digikey")

    print("\n" + "=" * 72)
    print("OSKAR — PRE-UAT PREFLIGHT CHECK")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}   ·   {len(names)} checks")
    print(f"  MOVEX_CONO={os.environ.get('MOVEX_CONO', '<unset>')}   "
          f"MOVEX_API_URL={os.environ.get('MOVEX_API_URL', '<unset>')}")
    print("=" * 72 + "\n")

    results: list[Result] = []
    for name in names:
        print(f"→ {name} ...", flush=True)
        start = time.time()
        try:
            res = CHECKS[name]()
        except Exception as exc:
            res = Result(name, FAIL, f"check itself raised: {exc}")
        res.seconds = time.time() - start
        results.append(res)
        mark = {PASS: "OK  ", FAIL: "FAIL", SKIP: "SKIP"}[res.status]
        print(f"  [{mark}] {res.name} ({res.seconds:.1f}s)")
        if res.detail:
            print(f"         {res.detail}")
        print()

    print("=" * 72)
    passed = [r for r in results if r.status == PASS]
    failed = [r for r in results if r.status == FAIL]
    skipped = [r for r in results if r.status == SKIP]

    for r in results:
        mark = {PASS: "OK  ", FAIL: "FAIL", SKIP: "SKIP"}[r.status]
        print(f"  [{mark}] {r.name}")

    print("-" * 72)
    print(f"  {len(passed)} passed · {len(failed)} failed · {len(skipped)} skipped")

    if failed:
        print("\n  NOT READY — the failures above are real boundary failures.")
    elif skipped:
        # A skip is not a pass. Reporting it as one is the exact "silence looks
        # like success" trap this whole plan exists to close.
        print("\n  INCOMPLETE — some checks could not run (missing prerequisites).")
        print("  Those boundaries are UNVERIFIED, not proven working.")
    else:
        print("\n  READY — every boundary verified against the real thing, today.")
    print("=" * 72 + "\n")

    return 1 if (failed or skipped) else 0


if __name__ == "__main__":
    sys.exit(main())
