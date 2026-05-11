# Council Transcript — Oskar Frontend Stack
**Date:** 2026-05-11  
**Project:** Oskar — Scanfil APAC ECN Workflow  
**Question:** Is Vite + React + TypeScript + Tailwind CSS the right frontend stack, or is there a meaningfully better alternative?

---

## Framed Question

Context: Scanfil APAC is building Oskar — an internal enterprise ECN (Engineering Change Notice) workflow application for a contract electronics manufacturer. Users are engineers and managers (not consumers). Deployed on-premise (IIS + Docker on Windows Server + Linux VM). No cloud CDN.

Key screens: ECN list/dashboard with filters, ECN create/edit form with complex nested items (BOM lines, routing operations, MPNs), multi-step approval workflow with role-based action buttons, real-time status via SSE, DC recovery panel.

Backend: FastAPI Python, JWT auth. SM-Portal (in production) uses Vite + React + TypeScript + Tailwind CSS. Visual coherence with SM-Portal required. Team: 1 lead engineer, primarily backend-focused. Target: late June 2026.

---

## Advisor Responses

### The Contrarian
The "visual coherence with SM-Portal" constraint is doing a lot of heavy lifting here, and nobody is questioning it hard enough. SM-Portal is already in production. That's a sunk cost argument dressed up as a technical requirement. The real question is: how much does cross-app visual coherence actually matter when engineers are the users? They navigate between tools constantly. They don't care if the table borders match.

Now for the actual flaw in the proposal: Tailwind without a component library is a trap for a solo backend-leaning dev. The question lists Tailwind CSS but then asks about shadcn/ui and Ant Design as alternatives — these aren't alternatives to the stack, they're the missing piece the stack desperately needs. Raw Tailwind for complex approval workflows, nested BOM form grids, and multi-state filter panels will consume weeks of a backend dev's time reinventing wheels. You will build a bad Ant Design from scratch.

The honest answer: if you're picking Vite + React + TypeScript, you must commit to Ant Design or shadcn/ui on day one, not optionally. Ant Design wins for this use case — it ships table virtualization, form validation, multi-step workflows, and modal management out of the box. A backend-leaning dev can be productive in days.

The deeper risk nobody is naming: the approval workflow state machine. React alone doesn't save you here. Without a proper state management approach (Zustand, TanStack Query, or XState for the workflow logic), the approval screen will become unmaintainable by month three regardless of which CSS framework you pick. Stack choice is the wrong obsession. State architecture is the real decision.

---

### The First Principles Thinker
The framing assumes the decision is "which frontend stack." It isn't. The real question is: why does Oskar need a custom frontend at all?

Strip the assumptions: SM-Portal already exists, is in production, and is built on exactly the stack being evaluated. Visual coherence is a stated requirement. Oskar's screens — filtered lists, complex forms, approval workflows, SSE updates — are not novel UI problems. They are solved problems within SM-Portal's existing architecture. The team is one backend-leaning engineer with a finite runway (late June target).

The first-principles answer: Oskar should be a module inside SM-Portal, not a separate application. Two separate frontends means two build pipelines, two deployment targets, two authentication integration points, two places to maintain shared components, and doubled cognitive overhead for a solo developer. That is not a tradeoff — it is pure waste.

If SM-Portal's architecture is modular (React lazy routes, feature-folder structure), adding Oskar as a new route namespace costs near zero infrastructure overhead while inheriting auth, API client patterns, component library, and deployment. The stack question only becomes real if there is a firm organizational reason Oskar must be a separate application — political boundary, different deployment server, separate release cadence. If any of those exist, state them explicitly. If none exist, the council is being asked to evaluate paint colors for a house that should share a wall with the one already built.

---

### The Expansionist
The question is wrong. The real question is: what stack makes Oskar extensible enough to become the foundation for Scanfil APAC's entire modernisation programme?

Confirm the React + Vite + Tailwind stack. That's not the interesting decision. The interesting decision is shadcn/ui over Ant Design, and the reason isn't aesthetics — it's ownership. shadcn/ui gives you the component source code. Every table, every modal, every form field lives in your repo. When Oskar evolves from ECN workflow into PLM integration, WMS handoffs, and eventually supplier-facing portals, you're not negotiating with an opinionated library's API surface. You own the primitives.

The upside everyone's undervaluing: Oskar isn't just an ECN tool. It's the React component foundation for every future Scanfil APAC internal app. The BOM line editor, the approval timeline component, the outbox error panel — these are reusable enterprise building blocks. If you build them as clean, composable shadcn/ui components from day one, you're simultaneously building the design system for WMS, PLM, and whatever comes after IFS migration.

React Query (TanStack Query) deserves a specific callout for SSE + optimistic updates. The real-time approval status panel becomes trivially reactive. Combined with Zod + React Hook Form for the complex nested BOM forms, the "solo backend-leaning dev" problem largely disappears — these libraries do the heavy cognitive lifting.

Skip Next.js. On-premise IIS deployment with a Node.js server layer is unnecessary friction. Vite + static build is a single dist/ folder. Deploy anywhere. No runtime to maintain. The ceiling here is high. Build the components right the first time and you've built Scanfil's frontend platform, not just one app.

---

### The Outsider
The framing of this question already reveals the answer you're going to choose, which is the problem. "Visual coherence with SM-Portal is required" is doing enormous hidden work here. That's not a technical constraint — it's a social one. Someone decided consistency matters more than fit-for-purpose, and now it's being treated as a hard requirement. Challenge that assumption before it locks you in.

Here is what an outsider sees immediately: you have one backend-focused engineer building complex approval workflows, nested BOM forms, and real-time panels. The bottleneck is not the framework — it's component density. Ant Design with plain React solves this faster than any combination involving "assemble your own component system with shadcn/ui and Tailwind." shadcn/ui is an excellent choice when you have design time. You don't.

The curse of knowledge here is that "Tailwind is simple" feels true to people who already know it. To a backend-leaning developer building a multi-step approval form with dynamic BOM line items, Tailwind means writing layout CSS again from scratch, just with different names. Ant Design's Table, Form, Modal, Steps components are immediately usable with zero styling decisions.

The on-premise deployment constraint eliminates the actual advantages of Next.js and Remix (SSR, edge functions, streaming). You'd be adopting their complexity with none of their benefits. Ant Design + React + TypeScript + Vite gives you 80% of your screens out of the box. The "visual coherence" concern can be addressed with a shared color palette — not a shared component system.

---

### The Executor
Use what SM-Portal already uses. Full stop. The stack is already decided by the production system sitting next to this one. Vite + React + TypeScript + Tailwind. The only real question is which component library to drop on top.

Monday morning action: Install shadcn/ui. Run `npx shadcn-ui@latest init`. Done in 20 minutes.

Here's why shadcn wins over Ant Design or MUI for this context: shadcn components are copy-paste into your codebase — no version conflicts, no fighting the library's opinions when your approval workflow needs non-standard behaviour. Tailwind is already there, so styling coherence with SM-Portal is automatic, not a negotiation. Complex nested forms (BOM lines, MPNs) are just React Hook Form + Zod — shadcn ships with those integrations documented.

What you don't do: Not Next.js — no SSR needed, adds deployment complexity on IIS, zero benefit. Not Remix — same problem, plus it's unfamiliar. Not SvelteKit — forces a parallel ecosystem alongside SM-Portal, doubles maintenance.

SSE in React is three lines. useEffect + EventSource. No library needed. The DC recovery panel and real-time status updates are not a stack decision — they're an afternoon of work in any framework. The actual bottleneck for a solo backend-leaning dev is the approval workflow state machine and the nested form validation — not the framework. React Hook Form with useFieldArray handles BOM lines directly. Pick shadcn's Table, Dialog, Form, and Sheet components and you have every screen template you need.

First step after shadcn init: scaffold the ECN list page using shadcn DataTable with TanStack Table. That's your proof-of-concept, built in a day.

---

## Peer Reviews

**Anonymization mapping:** A=Contrarian, B=First Principles, C=Expansionist, D=Outsider, E=Executor

### Review 1
- **Strongest:** C (Expansionist) — answers the actual question, commits to shadcn/ui with concrete strategic reasoning, correctly names TanStack Query + Zod + RHF as the real productivity enablers.
- **Biggest blind spot:** B (First Principles) — "fold into SM-Portal" ignores Oskar's separate deployment target (Linux VM) and release cadence.
- **All missed:** Authentication integration cost. JWT auth across two separate origins on-premise with no API gateway is a day-one architectural decision affecting every screen and API call.

### Review 2
- **Strongest:** C (Expansionist) — same as Review 1; adds that the platform foundation framing is correct given the broader modernisation programme.
- **Biggest blind spot:** B (First Principles) — ignored deployment reality: SM-Portal on SRXWEBAPP1 (IIS), Oskar on separate Linux VM. Already a closed question.
- **All missed:** Authentication integration cost. SM-Portal uses .NET JWT. Oskar FastAPI issues its own JWTs. Cross-origin SSO/token sharing is a day-one decision, not a polish item.

### Review 3
- **Strongest:** C (Expansionist) — commits to specific recommendation with clear strategic reason.
- **Biggest blind spot:** B (First Principles) — Oskar has different release cadence, different stakeholder group, explicitly positioned as foundation for broader modernisation programme.
- **All missed:** The June delivery deadline. With ~8 weeks and one engineer, none quantified the Ant Design vs. shadcn tradeoff against actual sprint capacity.

### Review 4
- **Strongest:** C (Expansionist) — only advisor thinking past immediate delivery; component ownership has compounding value across WMS, PLM, supplier portals.
- **Biggest blind spot:** B (First Principles) — ignores explicit context: separate deployment, separate release cadence, Python/FastAPI vs .NET.
- **All missed:** OpenAPI-to-TypeScript client generation (orval/openapi-typescript). Auto-generated type-safe API clients are the highest-leverage tooling decision absent from all responses.

### Review 5
- **Strongest:** C (Expansionist) — situates decision inside longer time horizon; shadcn as strategic ownership not preference.
- **Biggest blind spot:** B (First Principles) — ignores separate release cadence, separate deployment, organizational separation.
- **All missed:** OpenAPI-to-TypeScript client generation (orval/openapi-typescript). Highest-leverage tooling decision absent from all responses.

---

## Chairman Synthesis

### Where the Council Agrees
The stack is not the question. Every advisor converged: Vite + React + TypeScript is settled by SM-Portal's existence. No advisor recommended a divergent framework, and on-premise static deployment sealed it — Next.js and Remix add SSR complexity with zero benefit. SSE is not a stack decision; it is an afternoon of work with `useEffect` and `EventSource`. Raw Tailwind alone is a trap; a component library is mandatory.

### Where the Council Clashes
**shadcn/ui vs. Ant Design.** Contrarian + Outsider argued for Ant Design (component density, 8-week deadline). Expansionist + Executor argued for shadcn/ui (ownership, platform seed, Tailwind coherence). **Separate app vs. SM-Portal module.** First Principles argued for folding Oskar into SM-Portal. All peer reviews rejected this based on deployment reality.

### Blind Spots the Council Caught
1. **Authentication integration cost** — Two separate origins (SM-Portal .NET, Oskar FastAPI), on-premise, no API gateway. JWT strategy is a day-one architectural decision for role-based approval workflows.
2. **OpenAPI-to-TypeScript client generation** — `orval` or `openapi-typescript` against FastAPI's `/openapi.json` generates type-safe TanStack Query hooks + Zod schemas. Highest-leverage tooling decision; unmentioned by all five advisors.

### The Recommendation
**Stack: Vite + React + TypeScript + Tailwind CSS. Confirmed.**  
**Component library: shadcn/ui.** The platform argument wins over the deadline argument. Ant Design saves time initially but costs it when enterprise workflow logic needs non-standard behavior — and it always does.

Mandatory additions:
- React Hook Form + Zod (nested BOM forms)
- TanStack Query (SSE + optimistic updates)
- Zustand or XState (approval workflow state machine — the critical risk)

On auth: define the JWT strategy before writing any component. Options: shared signing key (simple, fragile), lightweight on-premise identity service (correct, more work), or separate sessions per app (acceptable for v1).

### The One Thing to Do First
Set up `orval` against FastAPI's `/openapi.json` before writing any component code. Configure it to generate TanStack Query hooks with Zod validation. Commit the generated client to the repo. 2 hours to configure. Removes more frontend risk than any component library decision on the board.
