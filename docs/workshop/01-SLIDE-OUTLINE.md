# Oskar Platform — Workshop Presentation Outline

> **Facilitator notes:** Each section header is a slide or slide group.
> Speaker notes are in blockquotes. Timing targets are in parentheses.
> Use `02-DIAGRAMS.md` to paste or render Mermaid diagrams live.

---

## Section 1 — Why Oskar Exists (15 min)

### Slide 1.1 — The Problem (Pain from Stargile)

**Title:** "What We're Replacing — and Why"

**Bullet points:**
- ECNs getting "stuck" with no visibility — engineers didn't know who was blocking them
- Movex writes happening with no retry — if the call failed, data was simply lost
- No email notifications — approvers learned about ECNs through Slack or word-of-mouth
- Zero audit trail — no way to prove who approved what and when for ISO audits
- No structured rejection path — a rejected ECN had to be recreated from scratch

> **Speaker note:** Ask the room: "Has anyone had an ECN bounce back with no explanation?"
> This framing makes the platform feel necessary, not just new.

---

### Slide 1.2 — The Business Context

**Title:** "Scanfil APAC — 170 People, 4 Certifications, 4 SMT Lines"

**Key facts:**
- Johor Bahru, Malaysia — EMS manufacturer, Scanfil Group (Finnish, 16 sites, 10 countries)
- Certifications: ISO 9001 · ISO 13485 (medical) · ISO 14001 · IATF 16949 (automotive)
- ~50 engineering users across 4 departments
- ERP: MOVEX / M3 on IBM i — the system of record for all product data. Oskar never owns data permanently.

> **Speaker note:** Emphasise that ISO 13485 (medical devices) is the most demanding standard.
> It requires written evidence of who approved every design change. Oskar makes this automatic.

---

### Slide 1.3 — What Oskar Is

**Title:** "Oskar — Engineering Intelligence Platform"

**Three-layer vision:**
- **Iteration 1 (now):** ECN workflow — structured approvals, Movex writeback, full audit chain
- **Iteration 2 (next):** BOM module — live BOM view, change impact analysis
- **Iteration 3 (future):** Supplier Intelligence — AI part identification, risk detection, alternatives

**Non-negotiable rules (the 3 that matter most for engineers):**
1. Movex is the Single Source of Truth — always
2. No Movex write without explicit human approval
3. Every transition is recorded in an immutable SHA-256 audit chain

---

## Section 2 — System Architecture (30 min)

### Slide 2.1 — System Context Diagram

**Diagram:** See `02-DIAGRAMS.md` → Diagram 1 (System Context)

> **Speaker note:** Walk through each actor and system. Emphasise: (1) All users authenticate
> via AD (LDAPS — no new accounts to create). (2) Oskar never calls Movex directly —
> everything goes through the `movex-rest-api` .NET bridge. (3) SM-Portal links to Oskar
> via a navigation link but has no shared auth or data coupling.

---

### Slide 2.2 — Tech Stack

**Title:** "Stack Choices and Why"

| Layer | Technology | Why |
|-------|-----------|-----|
| Backend | Python 3.12 / FastAPI | Async-first; LLM-compatible; rapid iteration |
| Database | PostgreSQL 16 | LISTEN/NOTIFY for real-time; RLS for security; no Redis needed |
| Task queue | Celery + PostgreSQL broker | Redis eliminated (ADR-007); simpler ops; same DB |
| Frontend | React 19.2 + TypeScript + Vite | Shared design tokens with SM-Portal; type safety |
| Auth | LDAPS + JWT | Single identity source; no separate user management |
| Containers | Docker + Docker Compose | Reproducible; Harbor registry on-prem |

> **Speaker note:** The Redis elimination (ADR-007) is worth a moment. We originally planned Redis
> for the Celery broker and session store. After analysis, PostgreSQL LISTEN/NOTIFY covers SSE,
> and the task volume (~10/day) doesn't justify the ops overhead of a second data store.

---

### Slide 2.3 — Deployment Diagram

**Diagram:** See `02-DIAGRAMS.md` → Diagram 5 (Deployment)

> **Speaker note:** The backend and frontend are separate containers behind IIS on SRXWEBAPP1.
> Engineers connect via VPN → IIS → Docker. The Harbor registry is on the same VM as the app.

---

### Slide 2.4 — Authentication Deep Dive

**Diagram:** See `02-DIAGRAMS.md` → Diagram 4 (Auth Flow)

**Key security decisions:**
- Access token stored **in memory only** — not `localStorage`. If the page refreshes, the
  refresh cookie re-issues a new one. This prevents XSS token theft.
- Refresh token uses **family detection** — if a refresh token is reused (possible theft), the
  entire family is invalidated.
- All tokens are hash-stored in `jti_blocklist` table. Logout is immediate and server-enforced.

> **Question for the room:** "Why can't we just use session cookies with the database?"

---

## Section 3 — ECN Domain & Workflow (30 min)

### Slide 3.1 — ECN in One Sentence

**Title:** "An ECN is the Formal Record That a Design Has Changed"

- Created by any engineer (Originator role)
- Reviewed by domain experts (SE/CE, then EM/QM/+conditionals)
- Controlled by the Document Controller (DC)
- Written to Movex automatically once DC approves
- Closed only after Movex confirms success

---

### Slide 3.2 — State Machine Diagram

**Diagram:** See `02-DIAGRAMS.md` → Diagram 2 (State Machine)

Walk through the happy path: `DRAFT → ENGINEERING_REVIEW → MANAGEMENT_REVIEW → DC_APPROVED → APPROVED → IMPLEMENTED → CLOSED`

Highlight:
- **MANAGEMENT_REVIEW** is a parallel block — EM, QM, and conditional roles all run concurrently
- **DC_APPROVED** is the single gate before any Movex write
- **ON_HOLD** can be entered from any non-terminal state and resumes exactly where it left off

---

### Slide 3.3 — The Parallel Approval Block Explained

**Title:** "Management Review — Parallel, Data-Driven, Flexible"

```
ECN → affects_product: true → PM step created automatically
     → affects_supply_chain: true → SC step created
     → affects_cost: false → FN step NOT created

All created steps must reach "approved" before auto-advance to DC_APPROVED
```

**Where is this logic?**  
Not in Python code — it's in `ecn_step_conditions` table (migration 0002, 7 seed rows for
facility `L`). Adding a new conditional role = one INSERT, no code change.

---

### Slide 3.4 — Transactional Outbox Pattern

**Diagram:** See `02-DIAGRAMS.md` → Diagram 3 (Outbox Flow)

**The guarantee:**  
"Either the ECN status AND the Movex data are consistent, or the system will keep retrying until they are."

Without the Outbox:
```
UPDATE ecn status=IMPLEMENTED
[crash]
Movex never gets updated — silent data drift
```

With the Outbox:
```
BEGIN TRANSACTION
  UPDATE ecn status=IMPLEMENTED
  INSERT movex_outbox (pending, mi_calls=[...])
COMMIT
-- Even if the worker crashes here, the outbox row survives --
Celery picks it up on restart → retries → completes
```

> **Speaker note:** This pattern (also called the "Reliable Messaging" pattern) is one of the
> most important architectural decisions in the system. It's why we don't have the Stargile
> problem of "did the Movex write actually happen?"

---

## Section 4 — Backend Internals (30 min)

### Slide 4.1 — Project Structure Tour

```
src/
├── main.py          ← FastAPI app, lifespan, middleware, routers
├── routers/         ← HTTP layer: auth, ecn_core, ecn_items, ecn_routing, parts, sse, admin, health
├── services/ecn/    ← Business logic: workflow, items, routing, commodity codes
├── workflow/        ← State machine (ECNWorkflowMachine) + audit hash
├── adapters/        ← ERP (Movex, IFS stub), Suppliers (DigiKey, Nexar), AI
├── tasks/           ← Celery workers: outbox processor, email, audit checkpoint
└── middleware/      ← Correlation ID injection, origin validation
```

> **Speaker note:** Walk through a request end-to-end: browser → PATCH /ecn/{id}/status →
> `routers/ecn_core.py` → `services/ecn/workflow.py` → `workflow/machine.py` →
> PostgreSQL transaction → SSE notify → Celery picks up outbox.

---

### Slide 4.2 — ERP Adapter Pattern

**Title:** "Movex Is Accessed Through an Abstraction — Not Directly"

```python
# Never do this
await db2_connection.execute("INSERT INTO MVXCOBJ.MRS001 ...")

# Always do this
await erp_adapter.write_bom_change(ecn_item)  # → MovexRestAdapter → movex-rest-api → MI
```

Why the adapter exists:
- Testability: `MockERPAdapter` in tests; no IBM i needed
- Future-proofing: IFSAdapter stub is already there for when Scanfil migrates
- Single change point: if the MI API changes, only `adapters/erp/movex.py` needs updating

---

### Slide 4.3 — Resilience Patterns

**Title:** "What Happens When Things Go Wrong"

| Scenario | Protection |
|---------|-----------|
| Movex MI call fails | `tenacity` retry + exponential backoff; circuit breaker (`pybreaker` fail_max=5) |
| Celery worker crashes | Outbox pattern; `pending` row survives restart |
| DigiKey API down | Circuit breaker; graceful degradation (returns partial data) |
| Concurrent ECN edits | Optimistic locking (`If-Unmodified-Since` → 409) |
| Token replay attack | JTI blocklist in DB; logout invalidates immediately |
| Sensitive data in logs | `structlog` secrets masking (password, token, secret fields) |

---

### Slide 4.4 — Observability

**Title:** "How You Debug When Something Goes Wrong"

Every request gets a `X-Correlation-ID` header (UUID), injected by `middleware/correlation.py`.
This ID propagates through:
- Every log line (`structlog` JSON)
- Celery task context
- movex-rest-api calls (passed as header)

To debug a failed Movex write:
1. Find the correlation ID in the frontend network tab
2. `grep correlation_id=<id> /var/log/oskar/backend.log`
3. Trace the full request → service → Celery → MI call chain

---

## Section 5 — Frontend Internals (30 min)

### Slide 5.1 — React App Structure

```
frontend/src/
├── pages/
│   ├── LoginPage.tsx        ← LDAPS login form
│   ├── ECNListPage.tsx      ← Filterable table with next-action badges
│   ├── ECNCreatePage.tsx    ← New ECN form
│   └── ECNDetailPage.tsx    ← Full ECN view + workflow actions
├── components/
│   ├── ecn/
│   │   ├── WorkflowPanel.tsx   ← Current status, action buttons
│   │   ├── ECNItemPanel.tsx    ← Item + MPN management
│   │   ├── RoleRow.tsx         ← Per-role approval UI
│   │   └── ActionModal.tsx     ← Approval/rejection form
│   └── ui/                  ← shadcn/ui component library
└── lib/
    └── ecn-workflow.ts      ← Client-side workflow state helpers
```

---

### Slide 5.2 — Role-Based UI Rendering

**Title:** "The UI Knows What You Can Do — Without Extra API Calls"

The JWT payload contains the user's AD groups. The frontend combines:
- **Group membership** (from JWT) → coarse role check (e.g., "is this user in the DC group?")
- **Per-ECN assignments** (from API) → fine-grained check (e.g., "is this user the QM for this ECN?")

Result: Action buttons appear only for the roles you can actually perform. The API enforces the
same rules server-side — the UI is a convenience, not a security boundary.

---

### Slide 5.3 — Real-Time Updates

**Title:** "How the Frontend Stays Current Without Polling Every Second"

1. **Primary:** SSE (`/api/v1/ecn/{id}/stream`) — PostgreSQL LISTEN/NOTIFY → backend pushes events → browser receives instantly
2. **Fallback:** HTTP polling every 15–30 s if SSE connection drops

This means: when DC approves an ECN, the Originator's screen updates within 1–2 seconds without refreshing.

---

### Slide 5.4 — Form Handling & Validation

**Title:** "React Hook Form + Zod — Type-Safe Forms"

```typescript
const schema = z.object({
  title: z.string().min(5, "Title too short"),
  facility: z.enum(["L"]),
  affects_product: z.boolean(),
  // ...
});

const form = useForm<z.infer<typeof schema>>({
  resolver: zodResolver(schema),
});
```

- Zod schema mirrors backend Pydantic schema — catch errors client-side before the API call
- React Hook Form handles form state, dirty tracking, and submission
- `useFormContext` passes form state down to nested components without prop-drilling

---

## Section 6 — Development Workflow (30 min)

### Slide 6.1 — Commit Convention

**Title:** "How We Commit"

```
feat(ecn): add on-hold/resume workflow transitions
fix(outbox): retry backoff not resetting on status change
test(workflow): add parallel management review block coverage
docs(adr): ADR-009 DC single gate rationale
chore(deps): bump pydantic to 2.10.3
```

Format: `type(scope): description`  
Types: `feat` | `fix` | `test` | `docs` | `refactor` | `chore` | `adr`  
CI will reject commits that don't follow this format.

---

### Slide 6.2 — Architecture Decision Records

**Title:** "Every Non-Obvious Decision Gets an ADR"

Located in `decisions/`. Each ADR has:
- **Status:** Proposed / Accepted / Superseded
- **Context:** Why was this decision needed?
- **Decision:** What was decided?
- **Consequences:** What does this enable? What does it constrain?

Examples: `ADR-007` (Redis elimination), `ADR-009` (DC single gate), `ADR-008` (optimistic locking)

> **Rule:** If you're about to do something that future engineers will ask "why did they do it
> that way?" — write an ADR first.

---

### Slide 6.3 — Testing Strategy

**Title:** "Test-First, Every Sprint"

| Level | Tool | What It Covers |
|-------|------|---------------|
| Unit | pytest + Pydantic | Workflow state machine, hash chain, serialisation |
| Integration | pytest + asyncpg | DB round-trips, RLS policy enforcement |
| API | pytest + httpx | Full request/response cycle with real DB |
| Security | pre-commit: gitleaks + pip-audit | Secret scanning, dependency CVEs |
| E2E | Playwright (Sprint 4 UAT) | User flows end-to-end |

```bash
# Run all tests
docker compose exec backend pytest -v

# Run only workflow tests
docker compose exec backend pytest tests/workflow/ -v

# Check test coverage
docker compose exec backend pytest --cov=src --cov-report=term-missing
```

**Target:** ≥ 80% coverage for all modules. New features must ship with tests.

---

### Slide 6.4 — Sprint Structure

| Sprint | Focus | Status |
|--------|-------|--------|
| 0 — Harness | Project setup, skills, architecture | ✅ Done |
| 1 — Platform Foundation | Auth, ECN CRUD, workflow, Docker | ✅ Done |
| 2 — ECN Workflow | Outbox, email, routing, SSE | ✅ Done |
| 3 — Parts Intelligence | Alias lookup, PN gen, autofill | ✅ Done |
| **4 — UAT + Compliance** | IQ/OQ/PQ, training, shadow mode | ⏳ Now |

---

## Section 7 — Security & Compliance (15 min)

### Slide 7.1 — Threat Model (STRIDE Summary)

| Threat | Mitigation |
|--------|-----------|
| **Spoofing** | LDAPS bind; JWT HS256; refresh token rotation |
| **Tampering** | SHA-256 linked audit chain; RLS INSERT-only on history |
| **Repudiation** | Immutable `ecn_transition_history`; every action recorded with actor |
| **Information Disclosure** | RLS row-level access; JWT audience claim; secrets masking in logs |
| **Denial of Service** | SSE 20-connection cap; Celery rate limiting; circuit breakers |
| **Elevation of Privilege** | AD group + per-ECN role double-check; self-approval prohibition |

---

### Slide 7.2 — ISO 13485 Compliance Controls

**Title:** "How Oskar Satisfies the Standard"

| Requirement | Control | Where |
|-------------|---------|-------|
| §6.2 Training records | `ecn_training_acknowledgements` created on CLOSED | `tasks/movex_outbox.py` |
| §7.3.9 Customer approval | `requires_customer_approval` flag + DC confirms before approving | `services/ecn/workflow.py` |
| §4.1 Management control | EM + QM always required at MANAGEMENT_REVIEW | `ecn_step_conditions` seed data |
| §4.2.5 Document control | Immutable audit chain + ECN number registry | `workflow/audit_hash.py` |

---

### Slide 7.3 — Things Engineers Must Never Do

**Title:** "The Rules — Non-Negotiable"

1. **Never hardcode secrets** — use `python-dotenv` (dev), Key Vault (prod)
2. **Never call Movex DB2 directly** — always go through `MovexRestAdapter`
3. **Never skip the audit chain** — every status change must go through `ECNWorkflowMachine`
4. **Never commit on behalf of another user** — JWT actor is always the authenticated user
5. **Never bypass the DC gate** — there is no "fast path" to Movex writes
6. **Never use CONO=100 (production) in dev** — dev and UAT always use CONO=300

---

## Section 8 — Wrap-Up (15 min)

### Slide 8.1 — What's Coming (Sprint 4)

- IQ/OQ/PQ validation sign-off (quality gate before go-live)
- Shadow mode — run Oskar in parallel with Stargile for 2 weeks
- LDAPS TLS confirmation (Manal / Devian — in flight)
- Drawing number endpoint (blocked on `movex-rest-api` MPDDOC implementation)
- Training acknowledgement UI (table exists; display pending)

### Slide 8.2 — How to Get Started

1. Clone the repo, copy `.env.example` → `.env.local`, fill in dev secrets from the team vault
2. `docker compose -f docker/docker-compose.dev.yml up -d`
3. `alembic upgrade head`
4. Browse `http://localhost:8000/docs`
5. Read `ai/memory/03-oskar-architecture.md` for the full context layer
6. Pick up a Sprint 4 task from `ai/tasks/sprint-backlog.md`

### Slide 8.3 — Q&A Primer

*Before opening to questions, ask:*

- "What part of the workflow was least clear?"
- "What would you have built differently — and have you read the ADR for it?"
- "Which test would you write first if you were starting on the codebase today?"
