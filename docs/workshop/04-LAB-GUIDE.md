# Oskar — Hands-On Lab Guide

**Pre-requisites:**
- Docker Desktop running (or Docker Engine on Linux)
- Git access to the Oskar repository
- `.env.local` filled in from `.env.example` (ask facilitator for dev secrets)
- PostgreSQL client (psql, DBeaver, or similar)

---

## Lab 0 — Environment Setup (10 min)

### 0.1 Start the dev stack

```bash
# From the Oskar project root
docker compose -f docker/docker-compose.dev.yml up -d

# Verify all containers are healthy
docker compose -f docker/docker-compose.dev.yml ps
```

Expected output: four services running — `postgres`, `backend`, `celery`, `frontend`.

### 0.2 Run migrations

```bash
docker compose -f docker/docker-compose.dev.yml exec backend alembic upgrade head
```

### 0.3 Verify the API is live

```bash
curl http://localhost:8000/health
# Expected: {"status": "ok"}

curl http://localhost:8000/api/v1/health/ready
# Expected: {"status": "ready", "db": "ok"}
```

### 0.4 Open Swagger UI

Navigate to `http://localhost:8000/docs` in your browser. You should see all API endpoints.

---

## Lab 1 — Authenticate and Explore (15 min)

### 1.1 Log in

```bash
curl -c cookies.txt -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "your.ad.username", "password": "your.ad.password"}'
```

Copy the `access_token` from the response. Export it:

```bash
export TOKEN="eyJ..."
```

### 1.2 List ECNs (empty on a fresh DB)

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/ecn/
```

### 1.3 Explore the schema in the database

```bash
# Connect to the dev PostgreSQL
psql postgresql://oskar:oskar@localhost:5432/oskar

# List tables
\dt

# Show the ECN status codes
SELECT * FROM ecn_step_conditions ORDER BY role_code;

# Show system role assignments
SELECT * FROM system_role_users;
```

**Question:** Which roles are seeded for facility `L`? Which ones are conditional?

---

## Lab 2 — Create and Submit an ECN (20 min)

### 2.1 Create a DRAFT ECN

```bash
curl -X POST http://localhost:8000/api/v1/ecn/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Lab ECN — Replace C220 capacitor",
    "description": "Change 100uF 16V electrolytic to 100uF 25V for improved reliability",
    "facility": "L",
    "affects_product": true,
    "affects_supply_chain": true,
    "affects_cost": false,
    "requires_customer_approval": false
  }'
```

Note the `id` from the response. Export it:

```bash
export ECN_ID="..."
```

### 2.2 Add a part item to the ECN

```bash
curl -X POST "http://localhost:8000/api/v1/ecn/$ECN_ID/items" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "item_number": "CAP-100U25V",
    "change_type": "change",
    "customer_part_number": "CUST-4421-CAP",
    "effectivity_date": "2026-07-01"
  }'
```

### 2.3 Submit the ECN

```bash
curl -X PATCH "http://localhost:8000/api/v1/ecn/$ECN_ID/status" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action": "submit", "notes": "Capacitor voltage upgrade for reliability improvement"}'
```

Verify the status changed:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/ecn/$ECN_ID" | python -m json.tool | grep status
```

**Expected:** `"status": 30` (ENGINEERING_REVIEW)

### 2.4 Check the audit chain

```bash
psql postgresql://oskar:oskar@localhost:5432/oskar \
  -c "SELECT from_status, to_status, actor, sha256_hash, sha256_prev FROM ecn_transition_history WHERE ecn_id = '$ECN_ID' ORDER BY transitioned_at;"
```

**Question:** What is in `sha256_prev` for the first row? Why?

---

## Lab 3 — Approve Through the Workflow (25 min)

You'll simulate multiple roles by using different user accounts (ask facilitator for test credentials
for `se_user`, `em_user`, `qm_user`, `dc_user`).

### 3.1 Engineering Review approval (SE)

```bash
export SE_TOKEN="..."  # log in as se_user

curl -X PATCH "http://localhost:8000/api/v1/ecn/$ECN_ID/status" \
  -H "Authorization: Bearer $SE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action": "approve_role", "role_code": "SE", "notes": "Technically sound"}'
```

### 3.2 Check Management Review parallel block started

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/ecn/$ECN_ID" | python -m json.tool | grep -A5 approval_steps
```

You should see `EM` and `QM` steps in `pending` state (and `SC` since `affects_supply_chain=true`).

### 3.3 Approve EM

```bash
export EM_TOKEN="..."  # log in as em_user

curl -X PATCH "http://localhost:8000/api/v1/ecn/$ECN_ID/status" \
  -H "Authorization: Bearer $EM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action": "approve_role", "role_code": "EM"}'
```

### 3.4 Approve QM

```bash
export QM_TOKEN="..."  # log in as qm_user

curl -X PATCH "http://localhost:8000/api/v1/ecn/$ECN_ID/status" \
  -H "Authorization: Bearer $QM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action": "approve_role", "role_code": "QM"}'
```

### 3.5 Approve SC

```bash
curl -X PATCH "http://localhost:8000/api/v1/ecn/$ECN_ID/status" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action": "approve_role", "role_code": "SC"}'
```

After the last required role approves, the status should automatically advance to `DC_APPROVED` (25).

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/ecn/$ECN_ID" | python -m json.tool | grep status
```

### 3.6 DC Approve

```bash
export DC_TOKEN="..."  # log in as dc_user

curl -X PATCH "http://localhost:8000/api/v1/ecn/$ECN_ID/status" \
  -H "Authorization: Bearer $DC_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action": "dc_approve", "notes": "All approvals complete, documentation correct"}'
```

**Expected status:** `50` (APPROVED)

---

## Lab 4 — Rejection Path (15 min)

Create a new ECN and test the rejection + resubmit flow.

### 4.1 Create and submit another ECN

```bash
curl -X POST http://localhost:8000/api/v1/ecn/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Lab ECN 2 — Test rejection",
    "description": "This ECN will be rejected for testing",
    "facility": "L",
    "affects_product": false,
    "affects_supply_chain": false,
    "affects_cost": false
  }'

export ECN2_ID="..."

# Add an item (required before submit)
curl -X POST "http://localhost:8000/api/v1/ecn/$ECN2_ID/items" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"item_number": "TEST-001", "change_type": "add"}'

# Submit
curl -X PATCH "http://localhost:8000/api/v1/ecn/$ECN2_ID/status" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"action": "submit"}'
```

### 4.2 Reject as SE

```bash
curl -X PATCH "http://localhost:8000/api/v1/ecn/$ECN2_ID/status" \
  -H "Authorization: Bearer $SE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action": "reject", "reason": "Missing technical justification for the change", "resolution": "restart"}'
```

Check status is `REJECTED` (65):

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/ecn/$ECN2_ID" | python -m json.tool | grep status
```

### 4.3 Resubmit

```bash
curl -X PATCH "http://localhost:8000/api/v1/ecn/$ECN2_ID/status" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action": "resubmit", "notes": "Added technical justification in description"}'
```

**Question:** What status is the ECN in now? What happened to the rejection record in the DB?

---

## Lab 5 — Write a Workflow Test (20 min)

Open `tests/workflow/test_machine.py` in your editor. Add a new test:

```python
def test_rejection_then_resubmit_returns_to_engineering_review(db_session, draft_ecn):
    """
    Verifies the rejection → resubmit path restores the ECN to ENGINEERING_REVIEW.
    The rejection record must be preserved in ecn_rejections.
    """
    machine = ECNWorkflowMachine(draft_ecn)
    
    # Submit
    machine.submit(actor="originator")
    assert draft_ecn.status == ECNStatus.ENGINEERING_REVIEW
    
    # Approve SE
    machine.approve_role(actor="senior_eng", role_code="SE")
    
    # Reject at management review
    machine.reject(actor="engineering_manager", reason="Missing compliance docs", resolution="restart")
    assert draft_ecn.status == ECNStatus.REJECTED
    
    # Resubmit
    machine.resubmit(actor="originator", notes="Added compliance docs")
    assert draft_ecn.status == ECNStatus.ENGINEERING_REVIEW
    
    # Rejection record is preserved
    rejection = db_session.query(ECNRejection).filter_by(ecn_id=draft_ecn.id).first()
    assert rejection is not None
    assert rejection.reason == "Missing compliance docs"
```

Run it:

```bash
docker compose -f docker/docker-compose.dev.yml exec backend \
  pytest tests/workflow/test_machine.py -v
```

**Extension challenge:** Add a test that verifies the SHA-256 chain is linked correctly after two transitions.

---

## Lab 6 — Parts Intelligence (10 min)

### 6.1 Reverse alias lookup

```bash
# Look up a customer part number → Scanfil internal stock code
curl "http://localhost:8000/api/v1/parts/alias?popn=CUST-4421-CAP&cuno=CUST001" \
  -H "Authorization: Bearer $TOKEN"
```

### 6.2 Suggest a part number

```bash
# Auto-suggest a Scanfil part number for a commodity + item class
curl "http://localhost:8000/api/v1/parts/suggest-pn?prgp=CAP&itcl=EL" \
  -H "Authorization: Bearer $TOKEN"
```

### 6.3 Autofill stock data from DigiKey

```bash
curl -X POST http://localhost:8000/api/v1/parts/autofill \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mpn": "UHE1H101MHD6", "manufacturer": "Nichicon"}'
```

**Question:** Where does the data come from? Which adapter handles DigiKey vs Nexar?

---

## Lab Summary

| Lab | What You Practiced |
|-----|--------------------|
| 0 | Environment setup — Docker, Alembic, health checks |
| 1 | Authentication flow — JWT, refresh token, DB schema exploration |
| 2 | ECN create + submit — outbox pattern, audit chain |
| 3 | Full approval path — parallel block, auto-advance |
| 4 | Rejection + resubmit — exception path |
| 5 | Writing workflow tests — ECNWorkflowMachine + pytest |
| 6 | Parts intelligence — supplier adapters, auto-fill |

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `401 Unauthorized` | Token expired | Re-login, export new `$TOKEN` |
| `409 Conflict` | Stale `If-Unmodified-Since` | Re-fetch the ECN, use the new `updated_at` |
| `422 Unprocessable Entity` | Missing required field | Check the Swagger schema for required fields |
| Celery not processing outbox | Worker not running | `docker compose ... exec celery celery -A src.tasks.celery_app inspect active` |
| DB migration error | Stale migration state | `alembic stamp head` then `alembic upgrade head` |
| `500 Internal Server Error` | Backend exception | `docker compose ... logs backend --tail=50` |
