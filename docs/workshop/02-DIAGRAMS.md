# Oskar — Workshop Architecture Diagrams

All diagrams use the workspace standard Mermaid config block.

---

## 1. System Context

> Who uses Oskar, what does it touch, and what sits outside it?

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
graph TB
    subgraph Users["Users (AD-authenticated)"]
        OR["Originator<br/>(Engineer)"]
        SE["Senior / Chief Engineer"]
        EM["Engineering Manager"]
        QM["Quality Manager"]
        PM["Product Manager"]
        SC["Supply Chain Manager"]
        FN["Finance Manager"]
        DC["Document Controller"]
        AD["Admin"]
    end

    subgraph Oskar["Oskar Platform"]
        FE["React Frontend<br/>(Vite + TypeScript)"]
        BE["FastAPI Backend<br/>(Python 3.12)"]
        DB["PostgreSQL 16<br/>(ECNs, Audit, Outbox)"]
        CW["Celery Worker<br/>(Outbox, Email, Audit)"]
        SS["SSE Stream<br/>(LISTEN/NOTIFY)"]
    end

    subgraph External["External Systems"]
        MX["MOVEX / M3<br/>(ERP — IBM i / DB2)"]
        MR["movex-rest-api<br/>(.NET 8 — MI bridge)"]
        AD_SRV["Active Directory<br/>(LDAPS — on-prem)"]
        SMTP["SMTP Server<br/>(10.10.0.155:25)"]
        DK["DigiKey API<br/>(Supplier data)"]
        NX["Nexar API<br/>(GraphQL — Parts)"]
        SMP["SM-Portal<br/>(Navigation link)"]
    end

    OR & SE & EM & QM & PM & SC & FN & DC & AD -->|HTTPS| FE
    FE -->|REST /api/v1| BE
    BE -->|asyncpg| DB
    BE -->|LISTEN/NOTIFY| SS --> FE
    BE -->|task queue| CW
    CW -->|Movex MI calls| MR --> MX
    CW -->|SMTP| SMTP
    BE -->|LDAPS bind| AD_SRV
    BE -->|httpx| DK & NX
    SMP -->|nav link| FE
```

---

## 2. ECN Workflow State Machine

> Every possible status and the transitions between them. Arrows are labelled with the trigger action.

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
stateDiagram-v2
    [*] --> DRAFT : create ECN

    DRAFT --> ENGINEERING_REVIEW : submit (OR)

    ENGINEERING_REVIEW --> MANAGEMENT_REVIEW : approve_role SE/CE (all required)
    ENGINEERING_REVIEW --> REJECTED : reject (SE/CE/DC)

    MANAGEMENT_REVIEW --> DC_APPROVED : complete_management_review\n(EM ✓ + QM ✓ + conditional roles ✓)
    MANAGEMENT_REVIEW --> REJECTED : reject (EM/QM/PM/SC/FN)

    DC_APPROVED --> APPROVED : dc_approve (DC)\n[+ customer_approval if flag set]
    DC_APPROVED --> REJECTED : reject (DC)

    APPROVED --> IMPLEMENTED : mark_implemented (DC)\n[Celery → Movex MI calls]
    APPROVED --> REJECTED : reject (DC)

    IMPLEMENTED --> CLOSED : auto (Celery)\n[training_acknowledgements created]

    REJECTED --> ENGINEERING_REVIEW : resubmit (OR)\n[if resolution = restart]
    REJECTED --> CANCELLED : withdraw (OR/DC)

    DRAFT --> CANCELLED : cancel (OR)

    note right of MANAGEMENT_REVIEW
        Parallel block:
        EM + QM always required
        PM if affects_product
        SC if affects_supply_chain
        FN if affects_cost
    end note

    note right of DC_APPROVED
        DC single gate (ADR-009)
        Human must approve
        before Movex write
    end note

    DRAFT --> ON_HOLD : on_hold (DC/AD)
    ENGINEERING_REVIEW --> ON_HOLD : on_hold (DC/AD)
    MANAGEMENT_REVIEW --> ON_HOLD : on_hold (DC/AD)
    DC_APPROVED --> ON_HOLD : on_hold (DC/AD)
    APPROVED --> ON_HOLD : on_hold (DC/AD)
    ON_HOLD --> DRAFT : resume (DC/AD)
    ON_HOLD --> ENGINEERING_REVIEW : resume (DC/AD)
    ON_HOLD --> MANAGEMENT_REVIEW : resume (DC/AD)
    ON_HOLD --> DC_APPROVED : resume (DC/AD)
    ON_HOLD --> APPROVED : resume (DC/AD)
```

---

## 3. Transactional Outbox — Event Flow

> How an approval becomes a Movex write without losing data if anything crashes.

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
sequenceDiagram
    participant DC as Document Controller
    participant API as FastAPI Backend
    participant DB as PostgreSQL
    participant CW as Celery Worker
    participant MR as movex-rest-api
    participant MX as Movex / M3

    DC->>API: PATCH /ecn/{id}/status (dc_approve)
    API->>DB: BEGIN TRANSACTION
    API->>DB: UPDATE ecn_instances SET status=APPROVED
    API->>DB: INSERT ecn_transition_history (SHA-256 chain)
    API->>DB: INSERT movex_outbox (pending, mi_calls=[...])
    API->>DB: COMMIT
    API-->>DC: 200 OK

    Note over CW,MX: Celery polls outbox every 30 s

    CW->>DB: SELECT outbox WHERE status=pending FOR UPDATE SKIP LOCKED
    CW->>DB: UPDATE outbox SET status=processing
    CW->>MR: POST /api/ecn/bom-change (MI call 1)
    MR->>MX: MRS001MI AddLine
    MX-->>MR: OK
    MR-->>CW: 200
    CW->>MR: POST /api/ecn/operation (MI call 2)
    MR-->>CW: 200
    CW->>DB: UPDATE outbox SET status=completed
    CW->>DB: UPDATE ecn_instances SET status=IMPLEMENTED

    Note over CW,DB: On failure: retry 30s → 5min → 30min<br/>Attempt 3 → alert DC<br/>Attempt 10 → abandoned
```

---

## 4. Authentication Flow

> How a user goes from browser login to an authorized API call.

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
sequenceDiagram
    participant U as User (Browser)
    participant FE as React Frontend
    participant API as FastAPI /auth
    participant LDAP as AD LDAPS
    participant DB as PostgreSQL

    U->>FE: Enter username + password
    FE->>API: POST /api/v1/auth/login {username, password}
    API->>LDAP: LDAPS bind (verify credentials)
    LDAP-->>API: OK + group memberships
    API->>DB: INSERT refresh_token (hashed, family_id)
    API-->>FE: {access_token} + Set-Cookie: refresh_token (HttpOnly)

    Note over FE: access_token stored IN MEMORY only<br/>(not localStorage — security rule)

    FE->>API: GET /api/v1/ecn/ Authorization: Bearer {token}
    API->>API: Verify JWT signature + expiry
    API-->>FE: ECN list

    Note over FE,API: On 401 (token expired):
    FE->>API: POST /api/v1/auth/refresh (sends cookie)
    API->>DB: Validate refresh token hash + family
    API->>DB: Rotate — INSERT new, mark old superseded
    API-->>FE: New access_token
```

---

## 5. Deployment Architecture

> How the stack is deployed on the Scanfil APAC infrastructure.

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
graph TB
    subgraph Internet_Edge["Client Network (VPN required)"]
        BROWSER["Engineer Browser"]
    end

    subgraph SRXWEBAPP1["SRXWEBAPP1 (Windows Server — IIS)"]
        IIS["IIS Reverse Proxy<br/>(HTTPS :443 → container)"]
    end

    subgraph OskarVM["apac-plm-ops.srxglobal.local<br/>(Ubuntu 24.04 LTS — 4 CPU / 16 GB / 100 GB)"]
        subgraph Docker["Docker Compose Stack"]
            FE_C["frontend container<br/>(React — Nginx)"]
            BE_C["backend container<br/>(FastAPI — Uvicorn)"]
            CW_C["celery container<br/>(Celery Worker)"]
            PG_C["postgres container<br/>(PostgreSQL 16)"]
        end
        HARBOR["Harbor Registry<br/>(image store)"]
    end

    subgraph IBMi["IBM i / AS400 (production ERP)"]
        MOVEX["Movex M3<br/>(MVXCOBJ schema)"]
    end

    subgraph SRXAPP["SRXAPP (Windows Server)"]
        MR_API[".NET 8 movex-rest-api<br/>(MI bridge)"]
    end

    BROWSER -->|HTTPS| IIS
    IIS --> FE_C
    IIS --> BE_C
    BE_C --> PG_C
    BE_C --> CW_C
    CW_C --> PG_C
    CW_C --> MR_API
    MR_API --> MOVEX
    HARBOR -->|pull images| Docker
```

---

## 6. Data Model — Entity Relationships

> Key tables and how they relate. Focus on the ECN lifecycle.

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
erDiagram
    ecn_instances {
        uuid id PK
        varchar ecn_number
        int status
        varchar facility
        bool requires_customer_approval
        bool affects_product
        bool affects_supply_chain
        bool affects_cost
        timestamptz updated_at
    }

    ecn_role_assignments {
        uuid id PK
        uuid ecn_id FK
        varchar role_code
        varchar assigned_to
        timestamptz superseded_at
    }

    ecn_approval_steps {
        uuid id PK
        uuid ecn_id FK
        varchar role_code
        varchar stage
        varchar status
        timestamptz decided_at
    }

    ecn_transition_history {
        uuid id PK
        uuid ecn_id FK
        int from_status
        int to_status
        varchar actor
        varchar sha256_hash
        varchar sha256_prev
        timestamptz transitioned_at
    }

    ecn_items {
        uuid id PK
        uuid ecn_id FK
        varchar item_number
        varchar customer_part_number
        varchar change_type
    }

    ecn_mpns {
        uuid id PK
        uuid item_id FK
        varchar mpn
        varchar manufacturer
        bool do_not_buy
        date eol_date
    }

    movex_outbox {
        uuid id PK
        uuid ecn_id FK
        varchar status
        int attempt_count
        jsonb mi_calls
        timestamptz next_attempt_at
    }

    ecn_step_conditions {
        uuid id PK
        varchar facility
        varchar role_code
        varchar condition_field
    }

    ecn_training_acknowledgements {
        uuid id PK
        uuid ecn_id FK
        varchar username
        timestamptz acknowledged_at
    }

    ecn_instances ||--o{ ecn_role_assignments : "has"
    ecn_instances ||--o{ ecn_approval_steps : "has"
    ecn_instances ||--o{ ecn_transition_history : "audit chain"
    ecn_instances ||--o{ ecn_items : "contains"
    ecn_instances ||--o| movex_outbox : "triggers"
    ecn_instances ||--o{ ecn_training_acknowledgements : "generates"
    ecn_items ||--o{ ecn_mpns : "has aliases"
    ecn_step_conditions }o--|| ecn_instances : "governs routing"
```
