# Council Transcript — Oskar Bulk Item Upload Architecture
**Date:** 17 June 2026  
**Project:** Oskar ECN Platform — Scanfil APAC

---

## Original Question

> Is the proposed bulk CSV/Excel import architecture (react-dropzone + SheetJS client-side → preview → /bulk endpoint) the best approach for Oskar? What failure modes are being missed, and is the UX pattern optimal?

---

## Framed Question (as sent to advisors)

**Context:** Oskar is an ECN (Engineering Change Notice) management platform for Scanfil APAC (electronics contract manufacturer). Stack: FastAPI (Python) + React 19 + TanStack Query + Radix UI + Tailwind CSS + Zod + PostgreSQL. Deployed on IIS + Windows Server.

**The Feature:** Bulk item upload via drag-and-drop CSV/Excel. Engineers upload a standardised template (already exists, ~14 mapped columns, < 500 rows, < 1MB). ECN must be in DRAFT status. Stop entirely on any validation error. Line numbers auto-assigned.

**Proposed Architecture:**
1. Frontend: react-dropzone + SheetJS (xlsx) → preview table → confirm → POST to backend
2. Backend: POST /api/v1/ecn/{ecn_id}/items/bulk → Pydantic → transactional INSERT
3. TypeScript parser: maps CSV columns, skips instruction rows 2-6, validates field lengths

**Questions:** (A) Client-side vs server-side parsing? (B) /bulk endpoint vs sequential loop vs background job? (C) Two-step preview/confirm UX optimal? (D) Failure modes missed? (E) Better library than SheetJS?

---

## Advisor Responses

### The Contrarian

The fatal flaw is the preview step becoming a trust trap. Engineers will glance at a 60-row preview table, see no red highlights, click Confirm, and then discover the backend rejected everything because of a Pydantic constraint the client-side validator didn't cover. You've now built a two-step flow where step one gives false confidence. The question isn't whether to do client-side validation — it's whether your client-side validation is byte-for-byte identical to your Pydantic model. It never is. Field length limits drift. Enum values get added server-side and forgotten on the client. That gap is where engineers lose 20 minutes at 4pm on a Friday.

The specific failure mode nobody asked about: Excel files from MOVEX exports carry numeric formatting on "text" fields. SheetJS will silently coerce a part number like `0034567` to the integer `34567`, stripping the leading zero. Your Pydantic model accepts it. Your MOVEX integration rejects it at sync time — three steps later, in a different session, with no connection back to the upload. That's not a recoverable UX problem, that's a data integrity hole.

Stop-on-error all-or-nothing is correct — but apply it after a dry-run server validation pass, not after a client-side pass. Force SheetJS to read all columns as raw strings: `{raw: false}`. Non-negotiable.

---

### The First Principles Thinker

What are you actually solving? Engineers have a standardised Excel template. They want its rows to become ECN items. That's it. The entire architecture debate is a distraction from a simpler question: where does the trust boundary sit?

You already answered it: the template is standardised, < 500 rows, engineers own the process. This is not a general file upload problem. It's a known-schema, trusted-user, small-payload data entry shortcut. Given that, client-side parsing is correct — not because SheetJS is great, but because you're not actually parsing arbitrary files. You're reading a template you control. Parse it where the feedback loop is tightest: in the browser, before any network round-trip. The preview step isn't a UX nicety, it's the core value proposition — the moment engineers see their data reflected back before commit is the moment they stop fearing bulk operations.

The assumption worth stripping away: You're treating this as an "upload feature." It isn't. It's a data entry acceleration layer over a form that already works. The right question is: what makes bulk entry feel as safe as row-by-row entry? Answer: immediate visibility + atomic commit. Both are already in your design.

The failure mode nobody named: The template itself will drift. Engineers will add columns, rename headers, use merged cells. Your parser will silently mismap or skip rows. The missing piece isn't a library choice — it's a header-fingerprint check on upload that detects template version mismatch and blocks with a clear message before the preview even renders. Ship that first.

---

### The Expansionist

The council question is scoped as a bulk upload feature. I see a template-to-ECN pipeline that's actually a data ingestion network waiting to be named.

The standardised Excel template is the real unlock here, not the upload mechanism. Engineers already work in that template format — which means you can extend the same parser to ingest from M3 MOVEX BOMs directly — MITMAS and MITPOP are already queryable via the DB2 direct endpoints in movex-rest-api. Instead of uploading a CSV, an engineer selects a parent assembly and Oskar pulls the BOM items automatically. The template becomes optional. Cross-ECN item reuse — once you've parsed 500 rows across 50 ECNs, Oskar has a queryable item library. Change velocity analytics — which product groups are being changed most?

Client-side SheetJS is correct for the POC because the preview-before-confirm UX is worth more than any backend-side flexibility gain. The two-step flow is the trust mechanism that makes engineers adopt it over manual entry.

The dedicated /bulk endpoint is right, but shape it as an idempotent upsert keyed on item_number within the ECN, not a pure insert. Retry safety is free if you design for it now.

---

### The Outsider

The template skip logic is a hidden landmine. Rows 2-6 are skipped as "instruction rows." What happens when an engineer opens the template, deletes the instructions because they find them annoying, and uploads it? Or when the template gets updated and the instruction block grows to row 8? Your parser is hardcoded to a physical row number in a file you don't control after distribution. Skip rows by content, not position. Match column headers by name. Everything that doesn't match a known header pattern gets ignored.

The two-step preview flow hides the real failure mode. Engineers will upload, see a preview, confirm — and then get a backend error because the ECN slipped out of DRAFT status between their preview and their confirm click. Someone else approved it in that window. You have no optimistic lock. The confirm button needs to check ECN status server-side before inserting, and the error message must say exactly why it failed, not "upload failed."

Duplicate detection is completely unspecified. If an engineer uploads the same file twice, what happens? Item number uniqueness within an ECN should be enforced at the database constraint level, not just application logic.

The encoding note is buried. MOVEX data on AS/400 often comes out in CP1252. Show the raw cell value in the preview, not a normalized version.

---

### The Executor

Parse server-side. Send the raw file as multipart/form-data. Use openpyxl + stdlib csv module. Zero new dependencies. If the template format ever changes, fix it in one place.

Dedicated /bulk endpoint. The sequential POST /items loop is a trap — 80 round-trips, 80 failure points, no atomicity. One endpoint, one transaction, one commit or rollback.

Two-step UX is correct but simplify it — skip the in-browser preview grid for the POC. Show errors as a numbered list. Engineers will tolerate a text list; building a preview grid is two days of work you don't need yet.

Failure modes: duplicate item_number in batch, CP1252 encoding (use chardet), stale ECN status check inside the transaction not before it. Drop SheetJS if parsing server-side.

---

## Peer Reviews

### Anonymization mapping
- Response A = The Contrarian  
- Response B = The First Principles Thinker  
- Response C = The Expansionist  
- Response D = The Outsider  
- Response E = The Executor  

### Reviewer consensus (all 5 independent reviews)

**Strongest response:** D (The Outsider) — unanimous. Identified three concrete ship-blocking bugs: positional row-skip logic, DRAFT status race condition with no optimistic lock, missing DB-level uniqueness constraint.

**Biggest blind spot:** C (The Expansionist) — unanimous. Pivoted to out-of-scope future vision instead of answering the architecture questions.

**What all five missed (each reviewer raised independently):**
1. Authorization/RBAC on the bulk endpoint — must match single-item add role checks. Compliance gap for regulated manufacturer.
2. Server-side file guards — content-type whitelist and size enforcement. VPN timeout handling.

---

## Chairman Synthesis

### Where the Council Agrees
- Dedicated /bulk endpoint: unanimous
- All-or-nothing transaction: unanimous  
- Two-step preview/confirm UX is correct in principle
- SheetJS `{raw: false}` is non-negotiable (leading-zero data integrity)
- DRAFT status race condition is a ship-blocking bug — check inside transaction with row-level lock
- Skip rows by header name matching, not position

### Where the Council Clashes
**Client-side vs server-side parsing** — the central dispute, resolved by doing both: SheetJS client-side for instant preview UX, raw file multipart POST to backend for authoritative dry-run Pydantic validation. Client-side validation is for UX speed only. Backend is the source of truth.

**Idempotent upsert vs pure insert** — deferred to Sprint 2. Pure insert + DB uniqueness constraint on (ecn_id, item_number) is correct for the POC.

### Blind Spots the Council Caught
1. **Authorization** — all 5 reviewers independently flagged this. Non-negotiable, day one.
2. **Server-side file guards** — content-type whitelist + size enforcement before parsing.
3. **Encoding** — CP1252 from AS/400. Show raw cell values in preview. Use chardet server-side for CSV.

### The Recommendation
- SheetJS `{raw: false}` + header-fingerprint check before preview renders
- Full preview grid with raw cell values and inline error highlighting (not optional)
- POST raw file as multipart/form-data → backend dry-run → INSERT in single transaction
- ECN DRAFT status: `SELECT ... FOR UPDATE` inside transaction
- DB: UNIQUE constraint on (ecn_id, item_number)
- Auth: identical RBAC as single-item add, day one
- File guards: server-side content-type whitelist + size limit
- Skip logic: header name matching, not row position

### The One Thing to Do First
Write the header-fingerprint validator before writing a single line of parsing logic. Define the canonical column header list as a constant. Block on mismatch before preview renders. Two hours of work that future-proofs all downstream parsing assumptions.
