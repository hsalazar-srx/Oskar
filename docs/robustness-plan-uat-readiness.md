# Oskar — Robustness & UAT-Readiness Plan

**Created:** 2026-08-13 · **Updated:** 2026-08-13 (added DigiKey/supplier boundary, full
workflow-scenario matrix, MAS agent involvement)
**Owner:** Lead Engineer (hector.salazar@srxglobal.com)
**Context:** Follow-up to I2-19 and LL-003 (`ai/evidence/lesson-learned-LL-003.md`) — this doc
exists so a new session can pick up this work without re-deriving the reasoning behind it.

**Scope note:** this plan is deliberately scoped to making Oskar a reliable replacement for
Stargile/PLM at the plants it serves today — it does not assume or require any decision about
multi-plant deployment. See `ai/tasks/platform-vs-migration-scope-analysis.md` for that separate,
explicitly-deferred question (parked for Stage 2). Nothing here is blocked on that decision.

---

## Why this exists

This session (2026-08-11/12/13) found and fixed two real bugs that shared a shape: **something
reported success while silently not doing what it claimed.**

1. **MSID envelope-parsing bug** (I2-21) — `process_outbox_entry`'s success check read
   `response.get("MSID")` at the wrong nesting level. Every dispatched MI write (BOM and
   routing) had been unconditionally marked completed regardless of what M3 actually returned,
   since the check was written. Found by chance while live-testing `add_bom_component` and
   cross-referencing movex-rest-api's own source.
2. **TDAT persistence bug** (I2-19) — `PDS002MI.UpdateComponent` reported `"success": true` and
   M3's raw response said `"OK"`, but the field it was called to set never actually changed.
   Found via a deliberate read-back check during live UAT-prep testing.

Both bugs passed the full test suite for weeks before being caught, because **every test that
exercised these paths mocked the exact boundary where the bug lived** (the MI response envelope
shape, the M3-side write). The test suite proved "the code does what I told it to do." It never
proved "the code actually works against the real, external thing it depends on."

A follow-up coverage review (2026-08-12/13) confirmed this is a systemic pattern, not a one-off:
notifications, MOVEX writes, and Celery are all tested the same way — real logic, mocked
boundary — with **zero automated regression protection at the boundary itself**. See "Current
state" below for what was actually checked (not assumed) for each area.

**The goal of this plan is not "more tests" — it's closing the specific boundary-verification
gap that let both of the above bugs hide.** Given the plan is to gain UAT user trust from the
start, the highest-leverage work is proving the boundaries that matter to a real user (does my
BOM change actually reach M3? does my approval email actually arrive?) are checked automatically,
not only by a human remembering to curl something by hand.

---

## Current state (verified 2026-08-13, not assumed — see grep/read evidence in the originating
conversation if this doc is stale by the time you read it)

| Area | What exists | What's missing |
|---|---|---|
| **Email notifications** | 18 unit tests (`tests/tasks/test_ecn_notifications.py`), `aiosmtplib.send` mocked | Never sent to a real (even test) mailbox. No proof the SMTP relay (`10.10.0.155:25`) actually accepts/delivers Oskar's mail, headers are correct, etc. |
| **MOVEX/CONO=300 writes** | Fully mocked adapter tests + manual, one-off curl verification (done by hand, repeatedly, across this whole project's live-testing sessions) | **Zero automated regression protection.** This exact blind spot is what let both bugs above ship undetected for weeks. |
| **Celery** | Every task (`process_outbox_entry`, alert tasks, etc.) called directly in-process in tests, `_get_conn`/`_run_mi_call`/SMTP all mocked | No test ever starts a real worker, or exercises the Postgres broker's `apply_async`/`eta`/`countdown` scheduling, or worker-crash/restart recovery. |
| **BOM CHANGE partial-failure** (Delete succeeds, AddComponent fails) | ✅ **Closed this session** — `tests/tasks/test_bom_change_partial_failure.py` (4 tests, all passing). Confirmed the existing retry/alert/`depends_on` machinery already handles this correctly. | — |
| **DigiKey / supplier data** | `src/adapters/suppliers/digikey.py` — real OAuth2 client, sandbox URL support already built in (`DIGIKEY_BASE_URL` defaults to prod, sandbox override exists). Tests in `tests/adapters/test_digikey_mounting_type.py`, `test_digikey_quota_and_encoding.py`, `test_supplier_chain.py` — all boundary-mocked (verified 2026-08-13, no `respx`/`httpx_mock` real-HTTP test found). | Same shape of gap as MOVEX: zero automated test ever hits the real DigiKey sandbox. OAuth2 token refresh, rate-limit-buffer behaviour (`DIGIKEY_RATE_LIMIT_BUFFER`), and response-shape drift are all only provable by a human running it by hand. |

Test suite as of `86844df`: 1058 passed, 2 skipped, 0 failed (fast suite). All 4 relevant
DB-backed integration tests for I2-19 pass individually (I2-18 workaround — Windows/Python 3.14
asyncio teardown bug means DB-backed integration test files must run one at a time; see I2-18 in
`ai/tasks/sprint-backlog.md`).

**Known infra constraint to plan around:** `tests/integration/conftest.py`'s `db_session`
fixture is intentionally rollback-only (one open transaction per test, never committed) for test
isolation. This means `process_outbox_entry` (which opens its own separate sync `psycopg2`
connection via `_get_conn()`) can **never see rows inserted through `db_session`** — they're
uncommitted from any other connection's point of view. Any plan to test `process_outbox_entry`
against a real DB needs either a dedicated non-rollback fixture, or to accept unit-level
(mocked-cursor) testing as the ceiling for that boundary. This was discovered while scoping the
BOM CHANGE partial-failure test above — don't rediscover it from scratch.

---

## Proposed plan, in priority order

### 1. MOVEX smoke test (highest priority)

A repeatable, scripted version of the manual verification done throughout this project's live
sessions: read a known BOM, write + verify (read-back) + cleanup a throwaway line, against real
CONO=300. Currently this has only ever been run by a human, by hand, when someone remembered to.

- **Why highest priority:** a UAT user hitting a silent write failure is the single most
  trust-destroying thing that can happen in this rollout, and this session proved (twice) that
  "the call reported success" is not sufficient evidence something actually worked.
- **Decisions needed before starting:**
  - Target item: reuse `LFAM050001` (the item used throughout this session's live testing,
    known-clean 11-line baseline) or set up a dedicated test item so nothing ever touches
    real-looking production data, even in a throwaway way?
  - Cadence: nightly scheduled run, run-before-each-UAT-session, or both?
  - Where do results/failures surface — a Slack/email alert, a dashboard, or just a log a human
    checks?
- **Suggested shape:** a script under `scripts/` (mirrors `scripts/movex_stub.py`'s existence as
  a dev-support script) that: (a) reads the target BOM via `GET /bom/{item}`, (b) asserts the
  expected baseline record count, (c) does an `AddComponent` + read-back-confirms + `Delete` +
  read-back-confirms-removed round trip on a throwaway `MSEQ`, (d) asserts final state matches
  starting state exactly. This is literally the sequence run by hand for I2-19's live
  verification — just needs to become code instead of a one-off terminal session.

### 2. DigiKey / supplier verification — quota-aware, not a routine smoke test

Same real-boundary risk as MOVEX (`src/adapters/suppliers/digikey.py` — real OAuth2 client,
never verified against a live response) but a **different approach is required**: DigiKey's
sandbox environment does not work (confirmed 2026-08-13 — do not plan around
`sandbox-api.digikey.com` as if it were a usable substitute for production, unlike MOVEX's
CONO=300 which genuinely is a safe, separate test company). Any real verification of this
adapter has to spend from the real, rate-limited **production** API quota
(`DIGIKEY_RATE_LIMIT_BUFFER`-governed) — so this cannot be a nightly/on-every-run automated
check the way the MOVEX smoke test can. It needs to be treated as a deliberately budgeted,
infrequent verification, not continuous regression protection.

- **Suggested shape:** a small number of fixed, known-stable part numbers looked up manually
  (or via a script run on-demand, not on a schedule) before major milestones — enough to catch
  "the adapter's parsing code no longer matches DigiKey's real response shape" (API drift) and
  "the OAuth2 flow still actually authenticates" — without burning meaningful quota on routine
  CI-style runs.
- **RESOLVED 2026-08-19 — budget confirmed: 1000 requests/month, allocated entirely to
  testing** (Lead Engineer). DigiKey's own `x-ratelimit-limit` header independently confirms
  `limit=1000`. Implemented as `scripts/digikey_verify.py`: 3 calls by default, 6 with
  `--full`. At a pre-milestone cadence that is a rounding error against the budget, and the
  script prints observed quota so consumption is visible rather than assumed.

- **Findings from the first live run (2026-08-19).** The verification immediately earned its
  keep — it found a real adapter bug that mocked tests could not:
  - **`search()` was broken for every possible call.** It issued `GET
    /products/v4/search/keyword?keywords=...`, but DigiKey v4 requires **POST with a JSON
    body** (PascalCase `Keywords`/`Limit`/`Offset`). Live-verified: GET → HTTP 404, POST →
    HTTP 200. The 404 is the *route* not matching, which at a glance is indistinguishable
    from "no results". Undetected because `search()` has no production callers yet (interface
    completeness only) — so the first caller would have hit a guaranteed failure. Fixed by
    adding a `_post` helper mirroring `_get` (quota check, token, rate-limit capture, retry,
    breaker) and switching `search()` to it.
  - **Everything else passed**: OAuth2 client-credentials, `get_part` field parsing
    (description/manufacturer/category/lifecycle), `digikey_part_number` resolution from
    `ProductVariations`, `mounting_type` normalisation, percent-encoding for MPNs containing
    `/`, `{}`-on-404 (which `SupplierChain` relies on to fall through to Nexar), and
    `health_check()`.
  - **Test-data caveat worth keeping:** `productdetails` matches the manufacturer part number
    *exactly*. The first draft used `LM358DR`, which 404s — DigiKey stocks onsemi's
    `LM358DR2G`. A near-miss MPN is indistinguishable from a broken adapter, so the pinned
    MPNs are verified-present and should be re-confirmed by hand if this script ever reports
    a not-found failure.
- Given the quota constraint, prioritize this **below** the MOVEX smoke test (which has a genuine
  safe test company and can run as often as useful) and the Celery/email work below, which don't
  have an external cost per run.
- If `SupplierChain` (the multi-supplier fan-out/fallback layer per `PRE-5-supplier-adapter-
  abc.md`) has other adapters beyond DigiKey, note whether any of them have a real sandbox —
  if so, that one can follow the MOVEX-style routine-smoke-test pattern instead of this
  quota-aware one.

### 3. Real Celery worker testing

Docker-compose profile (or an addition to the existing one) with an actual `celery worker`
process against the real Postgres broker (`ADR-007` — Postgres, not Redis), so tests can
`apply_async` a task and poll for real completion instead of calling the task function directly
in-process with everything mocked.

- Start narrow: one smoke test that enqueues a trivial task, confirms a real worker picks it up
  within N seconds. This alone would catch "the worker isn't running," "the broker config is
  wrong," "task isn't registered/imported" — categories of failure that unit tests structurally
  cannot catch since they never touch the actual queue.
- Second step, if time allows: run one real end-to-end outbox dispatch (a mocked `_run_mi_call`
  is fine here — the point is proving the worker/broker/scheduling machinery, not re-proving MI
  call correctness) through a real worker process.

### 4. Email deliverability

MailHog or Mailpit (lightweight, docker-friendly SMTP catcher with a web UI and an HTTP API for
assertions) standing in for the real relay in a test environment — proves mail is actually sent
and received with correct headers/recipients, not just that `aiosmtplib.send` was called with
the right arguments.

- Avoid pointing any automated test at the real `10.10.0.155:25` relay — real DC/EM inboxes
  should never receive test traffic.
- One test per notification trigger point is enough (submit, DC alert at attempt 3, EM
  abandoned alert, etc.) — the goal is proving deliverability works at all, not re-testing each
  trigger condition's logic (that's already covered by the existing 18 unit tests).

### 5. Full workflow-scenario matrix — ECN × Routing × MPN × BOM combinations

The existing test suite is strong on each area *individually* (ECN state machine: 47 tests
covering reject/cancel/hold/resume/reassign from every status; routing/MPN/BOM: adapter +
service + router + integration tests each). What's less proven is realistic **combinations** —
an ECN that touches routing AND BOM AND MPN changes together, going through rejection and
resubmission, with a partial Movex failure partway through. Stargile/PLM users lived in these
combined scenarios daily; Oskar's coverage of the individual dimensions doesn't guarantee the
combinations are covered.

Concrete combination scenarios worth scoping as explicit test cases (not exhaustive — a first
pass to build out with `validator-quality`, see below):

- An ECN with routing changes + BOM changes + new MPNs, all in one submission, reaches
  `dc_approve` — confirms `_queue_routing_operations_outbox`, `_queue_bom_changes_outbox`, and
  the MPN-master hook all fire correctly *together* for one ECN, with correct `depends_on`
  ordering across all three (not just within one area, which is what's tested today).
- An ECN rejected at `MANAGEMENT_REVIEW`, resubmitted with *different* BOM changes than the
  original submission — confirms the concurrency/snapshot-drift detection at `dc_approve`
  (I2-6) correctly re-evaluates against the resubmitted content, not stale data from the first
  submission.
- Two ECNs, same parent item, one touching BOM lines and the other touching routing operations
  on the same item concurrently — not a data race at the DB level (single Postgres, normal
  transaction isolation), but whether the *M3-side* write ordering matters (e.g. does a routing
  op write need the BOM write to land first, or are they independent at the M3 level — needs a
  real answer, not an assumption, per the LL-003 standard).
- An ECN placed `ON_HOLD` mid-workflow with BOM changes already staged, then resumed — confirms
  nothing about the hold/resume cycle drops or duplicates the staged `ecn_bom_changes` rows.
- A DELETE-type BOM change immediately followed by a CHANGE-type BOM change on the *same*
  component within one ECN (a real Stargile pattern — DC clarified a BOM edit into an explicit
  DELETE+re-ADD sequence) — confirms the depends_on chain doesn't create false ordering conflicts
  between two independent close/reopen pairs.

### 6. Involving MAS agents

Per the MAS manifest (`.github/agents/manifest.json`), two agents are directly relevant to this
work and worth engaging rather than doing everything as ad-hoc Claude Code sessions:

- **`validator-quality`** (quality-assurance domain) — the natural owner for scoping out the
  full combination-scenario matrix in §5 properly (this plan's list above is a first pass, not
  exhaustive) and for defining what "done" looks like for each boundary-verification item (1–4)
  — i.e. turning "MOVEX smoke test" into an actual acceptance checklist with pass/fail criteria,
  not just a script that runs.
- **`developer-python`** (scoped specifically to Oskar per its `companionProjects` list) — the
  right agent for actually implementing the scripts/fixtures/docker-compose changes once scoped,
  since it already carries Oskar-specific conventions context.
- **`expert-movex-dotnet`** (manufacturing-erp-integration domain) — worth consulting
  specifically on the M3-side write-ordering question in §5's third bullet (does routing-vs-BOM
  write order matter at the M3 level) — this is a question about M3/movex-rest-api internals,
  not Oskar's own code, and is exactly the kind of thing that should be verified against that
  agent's domain knowledge or the real RPG source, not assumed.

Suggested approach: use `validator-quality` to turn §5 into a properly scoped test matrix
(a deliverable, not just a list) before implementation starts, rather than writing scenario
tests ad-hoc one at a time.

### 7. On-demand "does it actually work" checklist — ✅ DELIVERED 2026-08-19

`scripts/preflight_check.py` — see `docs/runbooks/pre-uat-preflight.md` for the runbook.

**7 checks, ~20 seconds, all passing:** Movex write path · Celery worker liveness · crash
recovery (sweeper scheduled + registered) · email deliverability · ECN happy path E2E ·
ECN rejection path E2E · DigiKey (opt-in, 3 API calls).

Two design decisions worth recording, both aimed squarely at the failure mode this whole plan
exists to close:

- **A SKIP is never a PASS.** A missing prerequisite exits `1` and reports *INCOMPLETE — those
  boundaries are UNVERIFIED*, distinct from both READY and NOT READY. A checklist that
  reported green when it simply hadn't checked would reproduce the exact "silence looks like
  success" trap that let I2-19 and I2-21 hide.
- **Liveness is proven by doing, not by asking.** The worker check enqueues a real task and
  waits for it to be consumed, rather than using `celery inspect ping` — which does not work
  on the Postgres broker at all (see the healthcheck note below).

**Validated by deliberately breaking things**, not just by observing green:

| Injected fault | Result |
|---|---|
| worker stopped | `[FAIL] Celery worker` → NOT READY, exit 1 |
| Mailpit unreachable | `[SKIP] Email` → INCOMPLETE, exit 1 |
| sweeper name broken on the beat schedule | `[FAIL] Crash recovery` → NOT READY |

**New in this step:** `scripts/e2e_rejection_path.py` — §7 called for a rejection path, which
nothing else covered. It asserts the complementary property to the happy path: a rejected (or
still mid-workflow) ECN must write **nothing** to M3, verified against M3 itself. It then
resubmits and approves the same ECN as a control — asserting "nothing happened" is meaningless
without also proving the write *can* happen.

**Also fixed here:** the `oskar-worker-dev` healthcheck. It had reported `unhealthy` for three
days while demonstrably consuming tasks, because `celery inspect ping` rides a broadcast
mailbox Kombu's SQLAlchemy transport does not implement. Replaced with a `/proc` scan
(the slim image has neither `pgrep` nor `ps`, and `pidof celery` does not match because the
process is `python3.12 /usr/local/bin/celery ...`). A permanently-red healthcheck is worse
than none — it trains everyone to ignore it and masks a genuine outage.

### 8. Active Directory — the same gap, found in the auth layer — ✅ DELIVERED 2026-08-21

Not in the original plan. It surfaced while working through the AD group model with Manal, and
it is the same shape as §1–§4: **every LDAP test in the suite mocks `ldap3`**, so the suite
proved the filter was built correctly and the response parsed correctly, and could not prove
that AD accepts the filter, that the service account can read the Application Roles OU, or that
membership resolves at all. See ADR-013 for the decisions.

Two real defects were found by reading the auth path, both of the "silence looks like success"
kind this plan exists to close:

- **Nested membership resolved to nothing.** `srxglobal.com` nests Business Function groups
  (`grp-*`) into the Application Role groups (`ecn-*`), so a quality manager reaches
  `ecn-approver` via `grp-quality-manager`. `get_groups()` read the user's own `memberOf`
  attribute, which returns **direct membership only** — every nested user would have resolved to
  no roles and been locked out, while AD looked correctly configured to anyone checking. Now
  resolved with AD's `LDAP_MATCHING_RULE_IN_CHAIN`; direct membership still matches at depth
  zero, which is what `ecn-doc-controller` relies on.
- **A directory outage was indistinguishable from "this user has no groups."** Every LDAP method
  ended `except Exception: return []`. A DC outage, an expired service-account password or a
  rejected search all reached the user as `401 Invalid credentials` or a clean `403` — sending
  them to raise a permissions ticket against AD while the real fault was infrastructure. Exactly
  the I2-21 shape: a check that cannot tell "checked and found nothing" from "could not check."
  Now `LDAPDirectoryError` → **503**, never 401/403. A genuinely role-less user still returns
  `[]`, and an unset `mail` still returns `None` — those are real answers.

A third was found in passing: `list_application_groups()` filtered members by
`objectClass=user`, so the admin "who can approve?" view would have shown `ecn-approver` as
**empty** once nesting was in place. It now resolves effective membership through the chain.

**`scripts/ldap_verify.py`** (preflight check #5) is what proves any of this against the real
DC: service-account bind, nested resolution, direct resolution, no `grp-*` leaking into the
roles claim, `mail` populated, and a warning on any ECN role with no effective members.

Validated by breaking it, not by observing green:

| Injected fault | Result |
|---|---|
| Missing LDAP configuration | `REFUSED` → INCOMPLETE, exit 2 |
| No `LDAP_BIND_PW` | `[SKIP]` → INCOMPLETE, exit 1 |
| Unreachable DC | `[FAIL]` → NOT READY, exit 1 |

**Still UNVERIFIED against real AD** — and the check says so rather than passing. It needs the
test accounts from Manal, specifically ones whose ECN access comes *only* through nesting
(`LDAP_VERIFY_NESTED_USER`) plus one added directly (`LDAP_VERIFY_DIRECT_USER`). Without both,
preflight reports INCOMPLETE and exits non-zero.

**Also fixed here:** `preflight_check.py` crashed with `UnicodeEncodeError` on any Windows host.
It was validated inside the Linux dev container where stdout is UTF-8; the Windows console
defaults to cp1252 and the arrow characters raised before a single check ran — the checklist was
unusable from the machine most likely to run it. One `sys.stdout.reconfigure` at import.

**Known cost, not yet measured:** `get_groups()` now calls `_find_user_dn()` first, making a
login five LDAP connections rather than four, and the chain-walk is slower than reading an
attribute. Fine at ~50 users in principle, but this needs measuring against the real DC rather
than assuming. Connection reuse is the obvious fix.

---

## Explicitly out of scope for this plan

- Full CI/CD pipeline changes — this is about closing a specific verification gap, not a general
  CI overhaul.
- Fixing the underlying M3-side `TDAT` bug on `PDS002MI.UpdateComponent` — that's
  movex-rest-api's, not Oskar's, and Oskar no longer depends on it (see I2-19).
- The I2-18 Windows/Python 3.14 asyncio teardown bug in `db_session` — a real, separate,
  pre-existing issue; only relevant here because it constrains what kind of Celery/MOVEX
  integration tests are feasible without first fixing it.

---

## References

- `ai/evidence/lesson-learned-LL-003.md` — the incident that prompted this whole review
- `ai/tasks/sprint-backlog.md` — I2-19 (resolved), I2-18 (the asyncio teardown bug), I2-21 (the
  MSID parsing bug)
- `tests/tasks/test_bom_change_partial_failure.py` — this session's closed gap, useful as a
  template for the "prove the boundary, not just the logic" testing style this plan wants more of
- `docs/movex-rest-api-bom-contract.md` — movex-rest-api integration contract, useful background
  for the MOVEX smoke test's scope
- `ai/tasks/platform-vs-migration-scope-analysis.md` — the separate, deferred question of
  whether Oskar becomes multi-plant-deployable; explicitly not a dependency of this plan
