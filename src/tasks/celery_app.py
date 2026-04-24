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

from celery import Celery

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
)
