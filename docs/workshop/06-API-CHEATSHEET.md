# Oskar API — Quick Reference Cheat Sheet

**Base URL:** `http://localhost:8000` (dev) / `https://oskar.srxglobal.local` (UAT)  
**API version prefix:** `/api/v1/` — always required, never omit.  
**Auth header:** `Authorization: Bearer <access_token>`  
**Full docs:** `{base_url}/docs` (Swagger UI)

---

## Authentication

### Login

```bash
curl -X POST {BASE}/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "your.name", "password": "password"}'
```

Response: `{"access_token": "eyJ...", "token_type": "bearer"}`  
Side effect: `refresh_token` cookie set (HttpOnly).

### Refresh token

```bash
curl -b cookies.txt -X POST {BASE}/api/v1/auth/refresh
```

### Logout

```bash
curl -b cookies.txt -X POST {BASE}/api/v1/auth/logout \
  -H "Authorization: Bearer $TOKEN"
```

---

## ECN — Core Operations

### Create ECN (DRAFT)

```bash
curl -X POST {BASE}/api/v1/ecn/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "string (required)",
    "description": "string (required)",
    "facility": "L",
    "affects_product": false,
    "affects_supply_chain": false,
    "affects_cost": false,
    "requires_customer_approval": false
  }'
```

### List ECNs

```bash
# All ECNs
curl -H "Authorization: Bearer $TOKEN" {BASE}/api/v1/ecn/

# Filter by status (30 = ENGINEERING_REVIEW)
curl -H "Authorization: Bearer $TOKEN" "{BASE}/api/v1/ecn/?status=30"

# Filter by facility + overdue only
curl -H "Authorization: Bearer $TOKEN" "{BASE}/api/v1/ecn/?facility=L&overdue=true"

# Filter by next-action user
curl -H "Authorization: Bearer $TOKEN" "{BASE}/api/v1/ecn/?next_action_user=john.doe"
```

### Get ECN detail

```bash
curl -H "Authorization: Bearer $TOKEN" {BASE}/api/v1/ecn/{id}
```

### Workflow Transitions (all via status PATCH)

```bash
# Base command — replace ACTION and add fields as needed
curl -X PATCH {BASE}/api/v1/ecn/{id}/status \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action": "ACTION", "notes": "optional"}'
```

| Action | Required Role | From Status | To Status |
|--------|--------------|-------------|-----------|
| `submit` | OR | DRAFT | ENGINEERING_REVIEW |
| `approve_role` + `role_code` | Role holder | ENGINEERING_REVIEW | *(step advances)* |
| `approve_role` + `role_code` | EM/QM/PM/SC/FN | MANAGEMENT_REVIEW | *(step advances; auto-advance when last)* |
| `dc_approve` | DC | DC_APPROVED | APPROVED |
| `mark_implemented` | DC | APPROVED | IMPLEMENTED |
| `reject` + `reason` + `resolution` | Approver or DC | Any non-terminal | REJECTED |
| `resubmit` | OR | REJECTED | ENGINEERING_REVIEW |
| `on_hold` + `reason` | DC or AD | Any non-terminal | ON_HOLD |
| `resume` | DC or AD | ON_HOLD | *(pre_hold_status)* |
| `cancel` | OR | DRAFT | CANCELLED |
| `withdraw` | OR or DC | REJECTED | CANCELLED |

**Approve a role step:**

```bash
curl -X PATCH {BASE}/api/v1/ecn/{id}/status \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action": "approve_role", "role_code": "QM", "notes": "Quality requirements met"}'
```

**Reject with reason:**

```bash
curl -X PATCH {BASE}/api/v1/ecn/{id}/status \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "reject",
    "reason": "Missing FMEA documentation",
    "resolution": "restart"
  }'
```

`resolution` values: `restart` (resubmit possible) | `proceed` (cancelled immediately)

**Place on hold:**

```bash
curl -X PATCH {BASE}/api/v1/ecn/{id}/status \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "on_hold",
    "reason": "Waiting for customer drawing approval",
    "expected_resume_date": "2026-07-15"
  }'
```

### Optimistic Locking

All PATCH requests require the `If-Unmodified-Since` header to prevent concurrent edit conflicts:

```bash
# 1. Get the ECN and note updated_at
UPDATED_AT=$(curl -s -H "Authorization: Bearer $TOKEN" {BASE}/api/v1/ecn/{id} \
  | python -m json.tool | grep updated_at | cut -d'"' -f4)

# 2. Include header in PATCH
curl -X PATCH {BASE}/api/v1/ecn/{id}/status \
  -H "Authorization: Bearer $TOKEN" \
  -H "If-Unmodified-Since: $UPDATED_AT" \
  -H "Content-Type: application/json" \
  -d '{"action": "submit"}'
```

| HTTP Status | Meaning |
|-------------|---------|
| `200` | Success |
| `409 Conflict` | ECN was modified by someone else — re-fetch and retry |
| `428 Precondition Required` | Missing `If-Unmodified-Since` header |

---

## ECN — Items & Routing

### Add item to ECN

```bash
curl -X POST {BASE}/api/v1/ecn/{id}/items \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "item_number": "CAP-100U25V",
    "change_type": "change",
    "customer_part_number": "CUST-4421",
    "effectivity_date": "2026-07-01",
    "notes": "optional"
  }'
```

`change_type`: `add` | `change` | `delete`

### Update item

```bash
curl -X PATCH {BASE}/api/v1/ecn/{id}/items/{item_id} \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"effectivity_date": "2026-08-01"}'
```

### Add routing operation

```bash
curl -X POST {BASE}/api/v1/ecn/{id}/items/{item_id}/routing \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "operation_number": "010",
    "work_center": "SMT-01",
    "description": "Surface Mount Assembly",
    "setup_time": 30,
    "run_time": 5
  }'
```

---

## Parts & Supplier Intelligence

### Reverse alias lookup (customer PN → Scanfil stock code)

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "{BASE}/api/v1/parts/alias?popn=CUST-4421-CAP&cuno=CUST001"
```

### Suggest a Scanfil part number

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "{BASE}/api/v1/parts/suggest-pn?prgp=CAP&itcl=EL"
```

### Autofill stock info from DigiKey / Nexar

```bash
curl -X POST {BASE}/api/v1/parts/autofill \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mpn": "UHE1H101MHD6", "manufacturer": "Nichicon"}'
```

### Get procurement/product group matrix

```bash
curl -H "Authorization: Bearer $TOKEN" {BASE}/api/v1/parts/groups
```

### Auto-populate groups on an item

```bash
curl -X POST {BASE}/api/v1/parts/autofill-groups \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"item_id": "<uuid>", "mpn": "UHE1H101MHD6"}'
```

---

## Admin & Health

### Health checks

```bash
curl {BASE}/health                   # Unversioned (Docker HEALTHCHECK)
curl {BASE}/api/v1/health/live       # Liveness (DB connection)
curl {BASE}/api/v1/health/ready      # Readiness (all dependencies)
```

### Trigger daily digest email (DC only)

```bash
curl -X POST {BASE}/api/v1/admin/ecn-digest \
  -H "Authorization: Bearer $DC_TOKEN"
# Returns 202 Accepted — dispatches async
```

---

## Real-Time Updates (SSE)

```bash
# Subscribe to ECN changes (browser EventSource or curl)
curl -N -H "Authorization: Bearer $TOKEN" \
  {BASE}/api/v1/ecn/{id}/stream
```

Events: `ecn_status_changed` | `ecn_item_updated` | `ecn_role_assigned`

**Fallback:** If SSE is unavailable, the frontend polls `/api/v1/ecn/{id}` every 15–30 s automatically.

---

## Common Error Codes

| HTTP | Meaning | Fix |
|------|---------|-----|
| `400` | Bad request / invalid action | Check action name and current status |
| `401` | Unauthorized | Token expired — refresh |
| `403` | Forbidden | Your role cannot perform this action at this stage |
| `404` | ECN / item not found | Check the ID |
| `409` | Stale optimistic lock | Re-fetch ECN, get new `updated_at`, retry |
| `422` | Validation error | Check required fields in request body |
| `428` | Missing `If-Unmodified-Since` | Add header to all PATCH requests |
| `500` | Server error | Check backend logs |
