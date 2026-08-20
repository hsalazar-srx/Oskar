"""
OSKAR — Celery application instance (ADR-007, ADR-002)

Broker:  PostgreSQL via celery[sqlalchemy] — Redis eliminated (ADR-007)
Backend: PostgreSQL (same DB, celery_taskmeta table)

CELERY_BROKER_URL and CELERY_RESULT_BACKEND both point at the same
PostgreSQL database URL as DATABASE_URL.  The kombu_message table acts
as the task queue; celery_taskmeta stores task results.

Worker launch (production):
    celery -A src.tasks.celery_app worker --loglevel=info --concurrency=2

Beat launch (periodic tasks — ECN digest G-4):
    celery -A src.tasks.celery_app beat --loglevel=info

All task modules must be listed in CELERY_IMPORTS so the worker
discovers them without needing autodiscover_tasks.
"""

from __future__ import annotations

import os
import time

from celery import Celery
from celery.signals import task_postrun

# Database URL is the single source of truth for both broker and result backend.
# The celery[sqlalchemy] transport prefixes with "sqla+" to select Kombu's
# SQLAlchemy transport.  Result backend uses "db+" prefix.
_db_url = os.environ.get("DATABASE_URL", "postgresql+psycopg2://oskar:oskar@localhost:5432/oskar")

# Strip asyncpg driver if present — Kombu requires sync psycopg2
_sync_url = _db_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://").replace(
    "postgresql://", "postgresql+psycopg2://"
)

celery_app = Celery("oskar")

celery_app.conf.update(
    # Broker + backend — PostgreSQL (ADR-007)
    broker_url=f"sqla+{_sync_url}",
    result_backend=f"db+{_sync_url}",

    # Task discovery
    imports=[
        "src.tasks.movex_outbox",
        "src.tasks.audit_checkpoint",
        "src.tasks.ecn_notifications",
        "src.tasks.zpopextn_export",
    ],

    # Reliability: task is acknowledged only after it returns successfully.
    # Combined with idempotency_key on movex_outbox, this guarantees at-least-once
    # delivery without duplicate Movex writes.
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Serialisation
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Keep results long enough for DC Recovery UI to query them
    result_expires=86400 * 7,  # 7 days

    # Worker — conservative for a 2 vCPU / 4 GB VM (PRE-8)
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=200,

    # Beat schedule — periodic tasks
    beat_schedule={
        # Crash recovery for the Movex outbox. process_outbox_entry commits
        # state='processing' before its (slow) MI call and then relies on its
        # own failure branch to schedule the next retry — so a worker that
        # dies mid-dispatch strands the row forever: no retry, no DC/EM
        # alert, and an ECN parked at status 50 with nobody told. This sweep
        # is the ONLY thing that recovers those rows.
        #
        # 5 min cadence against a 30 min staleness threshold: recovery lands
        # within ~35 min of a crash, while the threshold (not the interval)
        # remains what protects live in-flight entries from being swept.
        "outbox-sweep-stale-processing": {
            "task": "oskar.tasks.sweep_stale_processing_entries",
            "schedule": 300.0,
        },
        "audit-chain-checkpoint-daily": {
            "task": "src.tasks.audit_checkpoint.checkpoint_audit_chain",
            "schedule": 86400.0,  # every 24 hours
        },
        "audit-chain-report-weekly": {
            "task": "src.tasks.audit_checkpoint.report_audit_checkpoint",
            "schedule": 604800.0,  # every 7 days
        },
        "ecn-overdue-escalation": {
            "task": "src.tasks.ecn_notifications.check_overdue_escalations_task",
            "schedule": 21600.0,  # every 6 hours — catches 48h and 96h thresholds within half a day
        },
        "ecn-digest-daily": {
            "task": "src.tasks.ecn_notifications.send_ecn_digest",
            "schedule": 86400.0,  # every 24 hours — replaces DBCHK_OpenECN (G-4)
        },
        "zpopextn-export-nightly": {
            "task": "src.tasks.zpopextn_export.export_default_mpns",
            "schedule": 86400.0,  # every 24 hours — successor to Stargile's PurchaseExtensionNightJob (ADR-012 R7)
        },
    },
)


# ---------------------------------------------------------------------------
# Liveness signal for the container healthcheck.
#
# Touches a file every time a task finishes, so "is this worker still
# consuming?" can be answered by the file's age. A process check cannot answer
# it: verified 2026-08-19, oskar-worker-dev reported "Up 28 minutes (healthy)"
# on a /proc scan while consuming nothing for 28 minutes — its processes were
# alive and its queue untouched. Celery's own ping is unusable here because
# Kombu's SQLAlchemy transport has no broadcast mailbox (ADR-007).
#
# Paired with the beat-scheduled sweeper (every 300s), a file older than 600s
# means two consecutive misses — the worker has stopped consuming.
# ---------------------------------------------------------------------------
_LIVENESS_FILE = os.environ.get("CELERY_LIVENESS_FILE", "/tmp/celery-last-task")


@task_postrun.connect
def _touch_liveness_file(**_kwargs: object) -> None:
    """Best-effort: never let liveness bookkeeping fail a task."""
    try:
        with open(_LIVENESS_FILE, "w") as fh:
            fh.write(str(time.time()))
    except Exception:
        pass
