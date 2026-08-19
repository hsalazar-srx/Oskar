# Runbook — Pre-UAT Preflight Check

**Created:** 2026-08-19 · **Owner:** Lead Engineer
**Implements:** `docs/robustness-plan-uat-readiness.md` §7
**Script:** `scripts/preflight_check.py`

## What this is

The concrete, repeatable answer to *"did we actually check this works today?"* —
run before each UAT milestone, not in CI.

Every check verifies a **real boundary**, not a mock. That is the entire point:
the two bugs that prompted this work (I2-19, I2-21) both passed a full mocked
test suite for weeks while silently doing nothing. A green unit suite proves the
code does what it was told; only these checks prove it works against the real
external thing.

## Running it

```bash
# 1. Bring up the supporting services (worker + mail catcher)
docker compose --env-file .env -f docker/docker-compose.dev.yml \
    --profile worker --profile mail up -d

# 2. Run the preflight
python scripts/preflight_check.py                 # 6 checks, no external cost
python scripts/preflight_check.py --with-digikey  # + live DigiKey (3 API calls)
python scripts/preflight_check.py --only movex,worker
```

Running from inside the dev container (how it was validated):

```bash
docker exec -e PYTHONPATH=/app \
  -e DATABASE_URL=postgresql://oskar:oskar_dev@oskar-test-db:5432/oskar_test \
  -e MAILPIT_API=http://host.docker.internal:8025 \
  -e MAILPIT_SMTP_HOST=host.docker.internal \
  oskar-app-dev python /app/scripts/preflight_check.py
```

Typical runtime: **~20 seconds** for all 6 checks.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | **READY** — every check passed |
| `1` | **NOT READY** (a check failed) or **INCOMPLETE** (a check could not run) |

**A SKIP is not a PASS.** A missing prerequisite (Mailpit down, no worker) exits
`1` and reports *INCOMPLETE — those boundaries are UNVERIFIED*. Treating a skip
as success is the exact "silence looks like success" trap this plan exists to
close.

## The checks

| # | Check | Proves | Cost |
|---|---|---|---|
| 1 | Movex write path | read → add → read-back → delete → read-back against **real M3**, asserting via fresh reads (never the write's own response) | free |
| 2 | Celery worker | a real worker is consuming from the Postgres broker | free |
| 3 | Crash recovery | the stale-`processing` sweeper is registered **and** scheduled | free |
| 4 | Email deliverability | mail is accepted by a real SMTP server with correct From/To | free |
| 5 | ECN happy path | approved ECN's **ordered** writes reach M3 via the real worker (S-3) | free |
| 6 | ECN rejection path | a rejected ECN writes **nothing** to M3 | free |
| 7 | DigiKey (opt-in) | live OAuth2 + response-shape drift | 3 API calls |

DigiKey is opt-in because it spends from a **1000 requests/month** budget
(confirmed 2026-08-19, and independently corroborated by DigiKey's own
`x-ratelimit-limit` header). At a pre-milestone cadence that is a rounding
error; everything else is free to run as often as useful.

## Interpreting failures

| Symptom | Likely cause | Action |
|---|---|---|
| `Movex write path` FAIL | M3 unreachable, or a genuine silent-write regression | Check `curl http://localhost:5000/health`. `CWBCO1004 - Remote address could not be resolved` = movex-rest-api cannot reach the AS/400 — infrastructure, not code |
| `Celery worker` FAIL | worker not running, or broker URL wrong | `docker compose --profile worker up -d`; check the worker's `DATABASE_URL` matches the app's |
| `Crash recovery` FAIL | sweeper unregistered or unscheduled | Regression in `celery_app.beat_schedule` or the `oskar.tasks.*` naming convention |
| `Email` SKIP | Mailpit not running | `docker compose --profile mail up -d` |
| `Email` FAIL | SMTP accepted but nothing delivered, or bad headers | Check `SMTP_FROM` — it must be set, and read (not `SMTP_SENDER`, which no code reads) |
| happy/reject FAIL | ordering regression, or leaked test data | If REFUSED: a previous run leaked `MSEQ 887/888` or `OPNO 888` — see cleanup below |

### Cleaning up leaked test data

The E2E scripts clean up in a `finally` block, but a hard interrupt or an M3
outage mid-run can leave residue. The scripts then **refuse to run** rather than
mutate an item whose state they do not recognise.

```bash
KEY=$(grep '^MOVEX_API_KEY=' .env | cut -d= -f2-)

# BOM lines (FDAT = the component's effective date)
curl -s -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -X POST http://localhost:5000/api/PDS002MI/Delete \
  -d '{"CONO":300,"FACI":"D","PRNO":"LFAM050001","STRT":"001","MSEQ":888,"FDAT":20260901}'

# Routing operation — NOTE FDAT=0: add_routing_operation sends no FDAT,
# so M3 stores the row with FDAT=0. Deleting with 20260901 silently no-ops.
curl -s -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -X POST http://localhost:5000/api/PDS002MI/Delete \
  -d '{"CONO":300,"FACI":"D","PRNO":"LFAM050001","STRT":"001","OPNO":888,"FDAT":0}'

# Verify the baseline is restored (expect 11 open lines)
python scripts/movex_smoke_test.py --read-only
```

## Traps worth knowing (all live-verified)

- **`celery inspect ping` does not work on this broker.** Kombu's SQLAlchemy
  transport does not implement the broadcast mailbox, so ping returns empty even
  when the worker is healthy — the container reported `unhealthy` for 3 days
  while processing tasks normally. Both the healthcheck and this preflight prove
  liveness by *enqueueing a real task*, never by ping.
- **`LstOperation` returns unstable results.** Three identical calls seconds
  apart returned 29, 29, then 40 records with a spurious `OPNO=0`. Never assert
  presence/absence from a list call — use `GetOperation` with the **exact**
  `FDAT` the row was created with.
- **The transaction config's `required` flags are not a validation spec.**
  `PDS002MI.json` marked `OPDS` optional while M3 rejects `AddOperation` without
  it. Treat that file as a field catalogue only.
- **M3 connectivity is not guaranteed.** A run may abort on `CWBCO1004`. The
  circuit breaker handles it and M3 is left clean — but distinguish an
  infrastructure blip from a real regression before acting on a failure.

## Baseline

The Movex checks target **`LFAM050001`** (facility `D`, CONO `300`), whose
known-clean baseline is **11 open BOM lines**:

```
MSEQ: 10, 20, 100, 105, 120, 140, 150, 160, 170, 180, 200
```

`scripts/movex_smoke_test.py` pins this and refuses to write if it does not
match. If the item legitimately changes, update `EXPECTED_BASELINE_MSEQ` in that
script — deliberately a code change, so it is a conscious decision rather than a
silently-moving target.
