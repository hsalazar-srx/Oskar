# OSKAR — ECN Workflow Diagrams
**For use in:** 2026-04-29 stakeholder meeting — Segment 4

---

## Diagram 1 — ECN State Machine (Full)

> Show this first. Walk through the main path (top), then show the side paths.

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
flowchart TD
    A([🖊 DRAFT\nOriginator authoring]) -->|Originator submits\nAll fields + ≥1 item populated| B([📬 SUBMITTED\nAwaiting DC completeness check])
    B -->|DC accepts| C([🔍 DC_REVIEW\nDocument Control checking])
    B -->|DC rejects| R([❌ REJECTED])
    C -->|DC passes to Engineering| D([⚙️ ENGINEERING_REVIEW\nSE / CE technical review])
    C -->|DC rejects| R
    D -->|SE / CE approves| E([👥 MANAGEMENT_REVIEW\nParallel approval block])
    D -->|SE / CE rejects| R

    subgraph parallel ["MANAGEMENT_REVIEW — All fire simultaneously"]
        EM["✅ Engineering Manager\n(always required)"]
        QM["✅ Quality Manager\n(always required — ISO 13485)"]
        PM["🔘 Production Manager\n(if routing / operation changes)"]
        SC["🔘 Supply Chain\n(if new parts / lead time changes)"]
        FN["🔘 Finance\n(if WAPC delta > threshold)"]
    end

    E --> parallel
    parallel -->|All required approvers complete| F([✔️ APPROVED\nMovex writes queued in outbox])
    parallel -->|Any single rejection| R

    F -->|Celery: all MI calls succeed| G([🏭 IMPLEMENTED\nMovex updated])
    F -->|MI call fails after 3 retries| F
    G -->|DC post-implementation check| H([🔒 CLOSED\nISO 13485 gate — terminal])

    R -->|Originator resubmits| B
    R -->|Originator withdraws| X([🚫 CANCELLED — terminal])

    A -->|Originator withdraws| X
    B -->|Originator withdraws| X

    E -.->|DC or Admin| OH([⏸️ ON_HOLD\nPrior status saved])
    OH -.->|DC or Admin resumes| E

    style A fill:#e8f4fd,stroke:#2196F3
    style B fill:#fff8e1,stroke:#FFC107
    style C fill:#fff8e1,stroke:#FFC107
    style D fill:#fff3e0,stroke:#FF9800
    style E fill:#e8eaf6,stroke:#3F51B5
    style F fill:#e8f5e9,stroke:#4CAF50
    style G fill:#e8f5e9,stroke:#4CAF50
    style H fill:#e0f2f1,stroke:#009688,color:#000
    style R fill:#fce4ec,stroke:#F44336
    style X fill:#f5f5f5,stroke:#9E9E9E
    style OH fill:#fafafa,stroke:#9E9E9E,stroke-dasharray: 5 5
    style parallel fill:#e8eaf6,stroke:#3F51B5
```

---

## Diagram 2 — Stargile vs OSKAR Status Mapping

> Use this to show Branko how the Stargile statuses map to OSKAR. Key message: Status 50 and 60 ("MOVEX_UPDATED_PENDING", "ACTION_NOTIFICATION_PENDING") disappear as user-visible states — they become infrastructure.

| Stargile Code | Stargile Name | OSKAR Equivalent | Why collapsed |
|---|---|---|---|
| 5 | PRELIMINARY | DRAFT (0) | No separate preliminary step needed |
| 10 | INITIATION | DRAFT (0) | Originator fills header in DRAFT |
| 15 | PRELIMINARY_REVIEW_PENDING | SUBMITTED (10) | DC completeness queue |
| 20 | PRE_APPROVAL_PENDING | DC_REVIEW (20) | DC acts |
| 25 | DC_CHECK_PENDING | DC_REVIEW (20) | Collapsed — single DC_REVIEW status |
| 30 | APPROVAL_PENDING | MANAGEMENT_REVIEW (40) | Parallel block |
| 35 | DC_APPROVAL_PENDING | DC_REVIEW / ENGINEERING_REVIEW | Sequential DC → SE gate |
| **50** | **MOVEX_UPDATED_PENDING** | **Infrastructure only — not user-visible** | Celery async task; users see APPROVED while it runs |
| 55 | COST_REVIEW_PENDING | MANAGEMENT_REVIEW (40) — FN role | Cost review is parallel not sequential |
| **60** | **ACTION_NOTIFICATION_PENDING** | **Infrastructure only** | Notifications fire automatically on transition |
| 65 | FINAL_APPROVAL_PENDING | MANAGEMENT_REVIEW (40) — CE endorsement | CE is part of the parallel block |
| 90 | ECN_COMPLETE | CLOSED (70) | — |
| 99 | ECN_CANCELLED | CANCELLED (80) | — |

**Key engineering insight:** In Stargile, Status 50 was a blocking synchronous Movex call with no feedback. If it timed out, the ECN stayed stuck with no error visible. In OSKAR, the Movex write is a Celery async task — it retries automatically, the DC sees every error with the exact Movex message, and the retry button is in the UI. No more stuck ECNs.

---

## Diagram 3 — Approval Chain (Sequential + Parallel)

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
sequenceDiagram
    actor OR as Originator
    actor DC as Document Controller
    actor SE as Senior Engineer
    actor EM as Eng. Manager
    actor QM as Quality Manager
    actor PM as Prod. Manager (cond.)
    actor SC as Supply Chain (cond.)
    participant SYS as OSKAR System
    participant M3 as Movex / M3

    OR->>SYS: Create ECN (DRAFT)
    OR->>SYS: Submit ECN
    SYS->>DC: Work item: Completeness check
    DC->>SYS: Accept → DC_REVIEW
    DC->>SYS: Pass to Engineering
    SYS->>SE: Work item: Technical review
    SE->>SYS: Approve → MANAGEMENT_REVIEW
    Note over EM,SC: All required approvers notified simultaneously
    SYS->>EM: Work item (always required)
    SYS->>QM: Work item (always required — ISO 13485)
    SYS-->>PM: Work item (if routing_changes=TRUE)
    SYS-->>SC: Work item (if new_parts=TRUE)
    EM->>SYS: Approve
    QM->>SYS: Approve
    PM-->>SYS: Approve (if required)
    SYS->>SYS: All approvals done → APPROVED
    SYS->>M3: MMS200MI.AddItmViaItmTyp (new item)
    SYS->>M3: PDS001MI.AddProduct (structure)
    SYS->>M3: PDS002MI.AddComponent (BOM lines)
    SYS->>M3: MMS025MI.AddAlias (MPN registration)
    M3-->>SYS: Confirm all writes → IMPLEMENTED
    DC->>SYS: Post-implementation check → CLOSED
    SYS->>OR: Training acknowledgement required
    SYS->>EM: Training acknowledgement required
    SYS->>QM: Training acknowledgement required
```

---

## Diagram 4 — Movex Write Gate (What happens at APPROVED)

> Use this when someone asks "when does it actually write to Movex?" This is the biggest Stargile improvement.

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
flowchart LR
    A[ECN reaches\nAPPROVED] --> B{New item?\nis_new_item=TRUE}
    B -->|Yes| C[MMS200MI\nAddItmViaItmTyp\nCreate item master]
    C --> D[MMS200MI\nAddItmFac\nCreate facility record]
    D --> E[MMS200MI\nAddItmWhs\nCreate warehouse record]
    E --> F[PDS001MI\nAddProduct\nCreate product structure]
    B -->|No — existing item| F
    F --> G[PDS002MI\nAddComponent / DeleteComponent\nBOM changes]
    G --> H{MPN aliases\nto register?}
    H -->|Yes| I[MMS025MI\nAddAlias\nRegister MPN in MITPOP]
    H -->|No| J[All writes complete]
    I --> J
    J --> K[IMPLEMENTED]

    L[Any MI call fails] --> M{Retry count?}
    M -->|Attempt 1-3| N[Retry: 30s → 5min → 30min]
    N --> G
    M -->|Attempt 3| O[DC alerted\nError in recovery panel]
    M -->|Attempt 10| P[ABANDONED\nEM alerted]

    style A fill:#e8eaf6,stroke:#3F51B5
    style K fill:#e8f5e9,stroke:#4CAF50
    style L fill:#fce4ec,stroke:#F44336
    style O fill:#fff8e1,stroke:#FFC107
    style P fill:#fce4ec,stroke:#F44336
```

**Key talking point for Nick:** Every MI call is in the audit log. If a BOM write fails — for any reason — Nick and DC see the exact Movex error message, not a mystery stuck state. The retry button is in the DC recovery panel. No more calling IT to manually rerun a Stargile push.

---

## Role Reference Card

> Print this for the meeting or paste into the role validation discussion.

| Role | Code | Required when | In parallel block? |
|------|------|--------------|-------------------|
| Document Controller | DC | Every ECN — all gates | Sequential gatekeeper |
| Originator | OR | Every ECN | Submits / resubmits / cancels |
| Senior Engineer | SE | ENGINEERING_REVIEW | Sequential reviewer |
| Chief Engineer | CE | ENGINEERING_REVIEW (escalation) | Co-reviews with SE |
| Engineering Manager | EM | MANAGEMENT_REVIEW | ✅ Always |
| Quality Manager | QM | MANAGEMENT_REVIEW | ✅ Always (ISO 13485) |
| Production Manager | PM | MANAGEMENT_REVIEW | ✅ If routing_changes or operation_changes |
| Supply Chain | SC | MANAGEMENT_REVIEW | ✅ If new_parts or lead_time_changes |
| Finance | FN | MANAGEMENT_REVIEW | ✅ If WAPC delta > threshold |
| Admin | AD | Platform admin only | — |
| Cost Accountant | CA | MANAGEMENT_REVIEW | Observer-plus (no veto) |

**Observer roles (notified but no approval):**

| Role | Code | When notified |
|------|------|--------------|
| R&D / Product Engineering | RD | ECN affects their product family |
| Test Engineering | TE | ECN includes document changes |
| Manufacturing Quality | MQ | ECN reaches CLOSED |
