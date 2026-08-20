#!/usr/bin/env python
"""Container healthcheck for the Celery worker — proves it is CONSUMING.

Exit 0 = healthy (a task finished recently), exit 1 = unhealthy.

Why not a process check: verified 2026-08-19, oskar-worker-dev reported
"Up 28 minutes (healthy)" from a /proc scan while consuming nothing for 28
minutes. Its processes were alive and its queue untouched, so the check was
green for exactly the outage it existed to catch.

Why not `celery inspect ping`: Kombu's SQLAlchemy transport (ADR-007) has no
broadcast mailbox, so ping is always empty even against a healthy worker — an
always-red check, which trains everyone to ignore it.

So: celery_app touches CELERY_LIVENESS_FILE on every task_postrun. Paired with
the beat-scheduled sweeper (every 300s), a file older than MAX_AGE means two
consecutive misses — the worker has stopped consuming.
"""
from __future__ import annotations

import os
import sys
import time

LIVENESS_FILE = os.environ.get("CELERY_LIVENESS_FILE", "/tmp/celery-last-task")
MAX_AGE_SECONDS = float(os.environ.get("CELERY_LIVENESS_MAX_AGE", "600"))


def main() -> int:
    if not os.path.exists(LIVENESS_FILE):
        # Nothing has completed yet. start_period covers normal startup; past
        # that, a worker that has never run a task is not consuming.
        print(f"no liveness file at {LIVENESS_FILE}", file=sys.stderr)
        return 1

    age = time.time() - os.path.getmtime(LIVENESS_FILE)
    if age >= MAX_AGE_SECONDS:
        print(
            f"last task completed {age:.0f}s ago (limit {MAX_AGE_SECONDS:.0f}s) "
            "— worker is not consuming",
            file=sys.stderr,
        )
        return 1

    print(f"last task completed {age:.0f}s ago")
    return 0


if __name__ == "__main__":
    sys.exit(main())
