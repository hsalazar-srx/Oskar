/**
 * Oskar E2E — low-level API helpers
 *
 * These helpers call the backend directly (bypassing the UI) to:
 *  - Obtain a JWT access token for a given dev user
 *  - Seed ECNs, items, and step-conditions so tests start from a known state
 *  - Advance an ECN to a target status without clicking through the UI
 *    (used as pre-conditions for tests that focus on a later stage)
 *
 * All functions take an `apiBase` string (e.g. "http://localhost:8000") so
 * tests can override it via the API_URL environment variable.
 */

import { APIRequestContext } from "@playwright/test"

export const API_BASE = process.env.API_URL ?? "http://localhost:8000"

// ── Token cache (per-user, valid for 60 min — reused within a test run) ────────

const _tokenCache: Record<string, string> = {}

export async function getToken(
  request: APIRequestContext,
  username: string,
  password = "dev-password",
): Promise<string> {
  if (_tokenCache[username]) return _tokenCache[username]

  const res = await request.post(`${API_BASE}/api/v1/auth/login`, {
    data: { username, password },
  })
  if (!res.ok()) {
    throw new Error(`Login failed for ${username}: ${res.status()} ${await res.text()}`)
  }
  const body = await res.json()
  _tokenCache[username] = body.access_token
  return body.access_token
}

export function clearTokenCache() {
  for (const key of Object.keys(_tokenCache)) delete _tokenCache[key]
}

// ── Auth header helper ─────────────────────────────────────────────────────────

export function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` }
}

// ── ECN factory ────────────────────────────────────────────────────────────────

export interface CreateECNOptions {
  title?: string
  facility?: string
  customer_number?: string
  is_new_item?: boolean
  routing_changes?: boolean
}

export async function createECN(
  request: APIRequestContext,
  token: string,
  opts: CreateECNOptions = {},
): Promise<{ id: string; ecn_number: string; updated_at: string }> {
  const res = await request.post(`${API_BASE}/api/v1/ecn/`, {
    headers: authHeaders(token),
    data: {
      title: opts.title ?? `E2E Test ECN ${Date.now()}`,
      facility: opts.facility ?? "L",
      customer_number: opts.customer_number ?? "CUST01",
      is_new_item: opts.is_new_item ?? false,
      routing_changes: opts.routing_changes ?? false,
      operation_changes: false,
      new_parts: false,
      lead_time_changes: false,
      change_to_documents: false,
      wapc_threshold_override: false,
      requires_customer_approval: false,
      regulatory_impact: false,
    },
  })
  if (!res.ok()) throw new Error(`createECN failed: ${res.status()} ${await res.text()}`)
  return res.json()
}

export async function addItem(
  request: APIRequestContext,
  token: string,
  ecnId: string,
  lineNumber = 10,
  itemNumber = "E2E-PART-001",
): Promise<void> {
  const res = await request.post(`${API_BASE}/api/v1/ecn/${ecnId}/items`, {
    headers: authHeaders(token),
    data: {
      item_number: itemNumber,
      item_name: "E2E test part",
      line_number: lineNumber,
      is_new_item: false,
      effectivity_type: "IMMEDIATE",
    },
  })
  if (!res.ok()) throw new Error(`addItem failed: ${res.status()} ${await res.text()}`)
}

// ── Transition helper ─────────────────────────────────────────────────────────

export async function fireTransition(
  request: APIRequestContext,
  token: string,
  ecnId: string,
  trigger: string,
  actorRole: string,
  extra: Record<string, string> = {},
): Promise<{ id: string; status: number; updated_at: string }> {
  // Fetch current updated_at for If-Unmodified-Since
  const ecnRes = await request.get(`${API_BASE}/api/v1/ecn/${ecnId}`, {
    headers: authHeaders(token),
  })
  if (!ecnRes.ok()) throw new Error(`GET ecn failed: ${ecnRes.status()}`)
  const ecn = await ecnRes.json()
  const rfc7231 = new Date(ecn.updated_at).toUTCString()

  const res = await request.patch(`${API_BASE}/api/v1/ecn/${ecnId}/status`, {
    headers: { ...authHeaders(token), "If-Unmodified-Since": rfc7231 },
    data: { trigger, actor_role: actorRole, ...extra },
  })
  if (!res.ok()) throw new Error(`fireTransition(${trigger}) failed: ${res.status()} ${await res.text()}`)
  return res.json()
}

export async function approveRole(
  request: APIRequestContext,
  token: string,
  ecnId: string,
  actorRole: string,
  notes?: string,
): Promise<void> {
  const res = await request.post(`${API_BASE}/api/v1/ecn/${ecnId}/approve`, {
    headers: authHeaders(token),
    data: { actor_role: actorRole, notes },
  })
  if (!res.ok()) throw new Error(`approveRole(${actorRole}) failed: ${res.status()} ${await res.text()}`)
}

// ── Pre-condition builders ─────────────────────────────────────────────────────
// Each returns { ecnId, updatedAt } so tests can pick up where they need.

/** DRAFT ECN with one item — ready to submit */
export async function ecnAtDraft(
  request: APIRequestContext,
  originatorToken: string,
  opts: CreateECNOptions = {},
) {
  const ecn = await createECN(request, originatorToken, opts)
  await addItem(request, originatorToken, ecn.id)
  return { ecnId: ecn.id, ecnNumber: ecn.ecn_number }
}

/** ENGINEERING_REVIEW — submitted by originator */
export async function ecnAtEngReview(
  request: APIRequestContext,
  originatorToken: string,
  opts: CreateECNOptions = {},
) {
  const { ecnId, ecnNumber } = await ecnAtDraft(request, originatorToken, opts)
  await fireTransition(request, originatorToken, ecnId, "submit", "OR")
  return { ecnId, ecnNumber }
}

/** MANAGEMENT_REVIEW — approved by SE */
export async function ecnAtMgmtReview(
  request: APIRequestContext,
  originatorToken: string,
  seToken: string,
  opts: CreateECNOptions = {},
) {
  const { ecnId, ecnNumber } = await ecnAtEngReview(request, originatorToken, opts)
  await fireTransition(request, seToken, ecnId, "approve_engineering", "SE")
  return { ecnId, ecnNumber }
}

/** DC_APPROVED — all management review roles approved */
export async function ecnAtDCApproved(
  request: APIRequestContext,
  originatorToken: string,
  seToken: string,
  qmToken: string,
) {
  const { ecnId, ecnNumber } = await ecnAtMgmtReview(request, originatorToken, seToken)
  // Approve QM step (the only required step in the test seed config)
  await approveRole(request, qmToken, ecnId, "QM")
  return { ecnId, ecnNumber }
}

/** REJECTED — rejected at engineering review */
export async function ecnAtRejected(
  request: APIRequestContext,
  originatorToken: string,
  seToken: string,
  opts: CreateECNOptions = {},
) {
  const { ecnId, ecnNumber } = await ecnAtEngReview(request, originatorToken, opts)
  await fireTransition(request, seToken, ecnId, "reject", "SE", {
    rejection_reason: "E2E test rejection",
  })
  return { ecnId, ecnNumber }
}
