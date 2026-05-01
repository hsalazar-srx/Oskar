# ADR-011 — CloudEvents 1.0 Event Envelope Standard

**Status:** Accepted
**Date:** 2026-05-01
**Owner:** Lead Engineer
**Reviewed by:**
  - @architect-system-design — Envelope design, event taxonomy mapping, schema evolution
  - @developer-integration — Integration compatibility: Siemens i3x, M3/Movex, MCP consumers
  - @expert-cybersecurity — Event integrity, replay protection, source attribution
  - @validator-quality — Audit trail completeness, ISO 27001 A.12.4 event logging
  - @expert-manufacturing-engineering — ECN event taxonomy alignment with real workflow
  - @expert-mes — Siemens i3x OPC-UA / CloudEvents compatibility, shop floor event patterns
**Type:** Architectural — type-1 (standard/convention; no runtime behaviour in Stage 1)

---

## Context

As OSKAR grows toward integration with Siemens i3x (mentioned by Nick, Production Manager,
April 29, 2026), external AI agents (MCP server, Stage 2), and Scanfil Group–level systems,
events emitted by OSKAR need a stable, interoperable envelope format.

Without a standard:
- Every new integration defines its own event shape.
- AI agents consuming ECN events cannot introspect `type`, `source`, or `time` reliably.
- Siemens i3x (which uses CloudEvents natively on its event bus) cannot consume OSKAR events
  without a custom adapter layer.
- The audit trail (ISO 27001 A.12.4.1) lacks event timestamps and source attribution in a
  machine-readable format.

**Siemens i3x relevance (@expert-mes):** Siemens Industrial Operations X (i3x) uses
CloudEvents 1.0 as its native event envelope on the OPC-UA PubSub and MQTT transport layers.
OSKAR publishing CloudEvents-compliant events means zero-adapter integration with i3x —
the production floor can consume ECN approval events directly to trigger work order holds,
BOM synchronisation, or tool change notifications.

---

## Decision

Adopt **CloudEvents 1.0** as the envelope standard for all OSKAR integration events.

**Stage 1:** Standard documented only. No runtime event bus exists.
**Stage 2:** `pg_notify` payloads (SSE path) wrapped in CloudEvents when the webhook
outbound system is built (`/api/v1/webhooks/`, migration 0008).

### Attribute Mapping

Required CloudEvents 1.0 attributes:

| Attribute | Type | OSKAR value |
|-----------|------|-------------|
| `specversion` | string | `"1.0"` |
| `id` | string | `UUID v4` — unique per event occurrence |
| `source` | URI-reference | `/oskar/ecn/{ecn_id}` or `/oskar/bom/{bom_id}` |
| `type` | string | `com.scanfil.oskar.{domain}.{event}` (see taxonomy below) |
| `time` | timestamp (RFC 3339) | Event timestamp, UTC |

Optional attributes used by OSKAR:

| Attribute | OSKAR usage |
|-----------|-------------|
| `datacontenttype` | `"application/json"` |
| `subject` | ECN number (e.g. `"ECN-2026-L-0042"`) or BOM ID |
| `dataschema` | URI of JSON Schema for the `data` field (Stage 2) |

### ECN Event Taxonomy

| Event type | `type` value | Trigger |
|------------|-------------|---------|
| ECN created | `com.scanfil.oskar.ecn.created` | `create_ecn()` — status → DRAFT (0) |
| ECN submitted | `com.scanfil.oskar.ecn.submitted` | Status → DC_APPROVED (25) |
| ECN in review | `com.scanfil.oskar.ecn.engineering_review` | Status → ENGINEERING_REVIEW (30) |
| Parallel approval started | `com.scanfil.oskar.ecn.approval_started` | Status → PARALLEL_APPROVAL (40) |
| Management approved | `com.scanfil.oskar.ecn.management_approved` | Status → MANAGEMENT_APPROVED (50) |
| Movex write queued | `com.scanfil.oskar.ecn.movex_write_queued` | `movex_outbox` row inserted |
| Movex write completed | `com.scanfil.oskar.ecn.movex_write_completed` | `movex_outbox` status → `sent` |
| ECN implemented | `com.scanfil.oskar.ecn.implemented` | Status → IMPLEMENTED (60) |
| ECN on hold | `com.scanfil.oskar.ecn.on_hold` | Status → ON_HOLD (65) |
| ECN closed | `com.scanfil.oskar.ecn.closed` | Status → CLOSED (70) |
| ECN rejected | `com.scanfil.oskar.ecn.rejected` | Status → REJECTED (80) |
| ECN cancelled | `com.scanfil.oskar.ecn.cancelled` | Status → CANCELLED (90) |

### AI/Agent Event Taxonomy (Stage 2)

| Event type | `type` value | Trigger |
|------------|-------------|---------|
| AI suggestion created | `com.scanfil.oskar.ai.suggestion_created` | `ai_suggestions` row inserted |
| AI suggestion accepted | `com.scanfil.oskar.ai.suggestion_accepted` | `accepted_at` set by human |
| AI suggestion rejected | `com.scanfil.oskar.ai.suggestion_rejected` | `rejected_at` set by human |
| Agent action proposed | `com.scanfil.oskar.agent.action_proposed` | `agent_actions` row inserted |
| Agent action approved | `com.scanfil.oskar.agent.action_approved` | `reviewed_by` set, status → `approved` |
| Agent action completed | `com.scanfil.oskar.agent.action_completed` | status → `completed` |

### Example Event

```json
{
  "specversion": "1.0",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "source": "/oskar/ecn/3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "type": "com.scanfil.oskar.ecn.management_approved",
  "time": "2026-05-01T08:30:00Z",
  "datacontenttype": "application/json",
  "subject": "ECN-2026-L-0042",
  "data": {
    "ecn_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "ecn_number": "ECN-2026-L-0042",
    "status": 50,
    "actor": "jsmith",
    "facility": "L"
  }
}
```

### Transport Mapping

| Transport | Stage | How |
|-----------|-------|-----|
| SSE (`/api/v1/ecn/{id}/stream`) | Sprint 2 | `pg_notify` payload is a subset of CloudEvents `data` — full envelope added in Stage 2 webhook layer |
| HTTP Webhook outbound | Stage 2 | `POST` to subscriber URL with CloudEvents JSON body |
| MQTT / OPC-UA PubSub | Stage 3 | CloudEvents over MQTT for Siemens i3x integration |
| A2A task bus | Stage 3 | CloudEvents as the message envelope between OSKAR and external agents |

### Security Considerations (@expert-cybersecurity)

**Event integrity:** Stage 2 webhook delivery should include an HMAC-SHA256 signature header
(`X-OSKAR-Signature: sha256=<hex>`) computed over the raw request body using a per-subscriber
secret stored in `webhook_subscriptions.signing_secret` (migration 0008).

**Replay protection:** `id` (UUID v4) + `time` (RFC 3339) together allow consumers to detect
and discard duplicate or replayed events. Consumers should maintain a sliding-window idempotency
cache keyed on `id`.

**Source attribution:** `source` URI provides machine-readable origin for audit trail (ISO 27001
A.12.4.1). Consumers can reject events with unexpected `source` values.

**Event confidentiality:** CloudEvents `data` must not include Movex pricing fields, customer
cost data, or supplier contract terms. ECN/BOM structural data (part numbers, descriptions,
statuses) is acceptable in internal events. External API events (Anthropic, i3x) require
management-approved data boundary review before enabling.

---

## Consequences

**Positive:**
- Siemens i3x integration requires no custom adapter — native CloudEvents consumption.
- AI agent (MCP server) and A2A consumers get a stable, introspectable event shape.
- ISO 27001 audit trail enriched with `id`, `source`, `time` in machine-readable form.
- CloudEvents is CNCF-graduated — stable, widely supported, no vendor lock-in.
- Stage 1 cost: zero (documentation only).

**Negative / Trade-offs:**
- `specversion`, `id`, `source`, `type`, `time` add ~150 bytes per event. Acceptable for
  ECN events (low-frequency human-paced workflow); review if IoT sensor events are added.
- Event schema versioning (`dataschema` URI) requires a schema registry or versioned JSON
  Schema files — deferred to Stage 2 when the webhook system is built.

---

## Related

- **ADR-007** — Redis elimination. `pg_notify` is the Stage 1 event mechanism; CloudEvents
  wraps it in Stage 2.
- **ADR-010** — AIProvider abstraction. AI suggestion events follow the taxonomy in §AI/Agent
  Event Taxonomy above.
- **ADR-002** — Transactional Outbox. `movex_outbox` state transitions map to CloudEvents
  types `ecn.movex_write_queued` and `ecn.movex_write_completed`.
- **MAS `governance/mas-rules.yaml`** — `agent_actions.authority_level` values map directly
  to CloudEvents `com.scanfil.oskar.agent.*` event types for A2A routing.
