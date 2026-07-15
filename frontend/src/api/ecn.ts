import axiosInstance from "@/api/axios"

// ── Shared types ──────────────────────────────────────────────────────────────

export interface GroupEntry {
  procurement_group: string
  product_group: string
  commodity_codes: string[]
}

export interface SuggestPnResponse {
  suggested_pn: string
  procurement_group: string
  product_group: string
  cuno: string
  commodity_code: string
  sequence: number
}

export interface AutofillResult {
  item_name: string | null
  mounting_type: string | null
  unit_of_measure: string | null
}

export interface CustomerEntry {
  cuno: string
  name: string | null
}

// ── ECN core ──────────────────────────────────────────────────────────────────

export async function fetchECN(id: string) {
  const { data } = await axiosInstance.get(`/api/v1/ecn/${id}`)
  return data
}

export async function fetchItems(id: string) {
  const { data } = await axiosInstance.get(`/api/v1/ecn/${id}/items`)
  return data as { id: string; item_number: string; item_name: string; customer_alias: string | null; is_new_item: boolean }[]
}

export async function fireTransition(
  ecnId: string,
  trigger: string,
  actorRole: string,
  updatedAt: string,
  extra?: Record<string, string>,
) {
  const doRequest = (ts: string) =>
    axiosInstance.patch(
      `/api/v1/ecn/${ecnId}/status`,
      { trigger, actor_role: actorRole, ...extra },
      { headers: { "If-Unmodified-Since": new Date(ts).toUTCString() } },
    )

  try {
    const { data } = await doRequest(updatedAt)
    return data
  } catch (err: any) {
    // FastAPI wraps 409 detail as { detail: { code, current_updated_at } }
    const freshTs: string | undefined = err?.response?.data?.detail?.current_updated_at
    if (err?.response?.status === 409 && freshTs) {
      const { data } = await doRequest(freshTs)
      return data
    }
    throw err
  }
}

export async function approveRole(ecnId: string, actorRole: string, notes?: string) {
  const { data } = await axiosInstance.post(`/api/v1/ecn/${ecnId}/approve`, {
    actor_role: actorRole,
    notes: notes ?? null,
  })
  return data
}

export async function assignRole(ecnId: string, roleId: string, username: string, actorRole: string) {
  const { data } = await axiosInstance.post(`/api/v1/ecn/${ecnId}/role-assignments`, {
    role_id: roleId,
    username,
    actor_role: actorRole,
  })
  return data
}

// ── ECN items ─────────────────────────────────────────────────────────────────

export async function fetchItem(ecnId: string, itemId: string) {
  const { data } = await axiosInstance.get(`/api/v1/ecn/${ecnId}/items/${itemId}`)
  return data
}

export async function fetchGroups() {
  const { data } = await axiosInstance.get("/api/v1/parts/groups")
  return data as GroupEntry[]
}

export async function suggestPn(
  ecnId: string,
  procurementGroup: string,
  productGroup: string,
  commodityOverride?: string,
): Promise<SuggestPnResponse> {
  const params: Record<string, string> = {
    ecn_id: ecnId,
    procurement_group: procurementGroup,
    product_group: productGroup,
  }
  if (commodityOverride) params.commodity_override = commodityOverride
  const { data } = await axiosInstance.get("/api/v1/parts/suggest-pn", { params })
  return data
}

export async function fetchCustomers(): Promise<CustomerEntry[]> {
  const { data } = await axiosInstance.get("/api/v1/customers")
  return data as CustomerEntry[]
}

/**
 * POST /api/v1/parts/autofill (dry_run=true)
 * Looks up the item's default MPN via the DigiKey/Nexar supplier chain and
 * returns suggested field values for user review — dry_run means the backend
 * does NOT write to ecn_items; the caller applies fields via updateItem only
 * if the user accepts the preview. Returns all-null fields when no supplier
 * has a match (or DigiKey's production quota guard has tripped) — the two
 * cases aren't distinguishable from the response and should both render as a
 * plain "no match found" state.
 */
export async function autofillItem(
  ecnId: string,
  itemId: string,
  itemNumber: string,
): Promise<AutofillResult> {
  const { data } = await axiosInstance.post("/api/v1/parts/autofill", {
    ecn_id: ecnId,
    item_id: itemId,
    item_number: itemNumber || null,
    dry_run: true,
  })
  return {
    item_name: data.item_name ?? null,
    mounting_type: data.mounting_type ?? null,
    unit_of_measure: data.unit_of_measure ?? null,
  }
}

// Private — only used by create/update below
function stripEmpty<T extends Record<string, unknown>>(obj: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(obj).filter(([, v]) => v !== "" && v !== undefined)
  ) as Partial<T>
}

export async function createItem(ecnId: string, lineNumber: number, body: Record<string, unknown>) {
  const { data } = await axiosInstance.post(`/api/v1/ecn/${ecnId}/items`, {
    ...stripEmpty(body),
    line_number: lineNumber,
  })
  return data
}

export async function updateEcn<T extends object>(ecnId: string, body: T, updatedAt: string) {
  const { data } = await axiosInstance.patch(
    `/api/v1/ecn/${ecnId}`,
    body,
    { headers: { "If-Unmodified-Since": new Date(updatedAt).toUTCString() } },
  )
  return data
}

export async function updateItem(ecnId: string, itemId: string, body: Record<string, unknown>) {
  const { data } = await axiosInstance.patch(
    `/api/v1/ecn/${ecnId}/items/${itemId}`,
    stripEmpty(body),
  )
  return data
}

/**
 * POST /api/v1/ecn/{ecnId}/items/bulk
 * Sends the raw file as multipart/form-data. The backend parses, validates
 * (Pydantic dry-run), and inserts all rows in one atomic transaction.
 * Throws on any HTTP error so the caller can display the error detail.
 */
export async function bulkCreateItems(ecnId: string, file: File) {
  const form = new FormData()
  form.append("file", file)
  const { data } = await axiosInstance.post(
    `/api/v1/ecn/${ecnId}/items/bulk`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } },
  )
  return data
}

// ── Routing operations ────────────────────────────────────────────────────────

export interface RoutingOp {
  id: string
  ecn_item_id: string
  operation_number: number
  operation_description: string
  work_centre: string
  run_time: number
  setup_time: number | null
  change_type: "ADD" | "UPDATE" | "DELETE"
  movex_snapshot: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface RoutingOpBody {
  operation_number: number
  operation_description: string
  work_centre: string
  run_time: number
  setup_time?: number | null
  change_type: string
}

export async function fetchRoutingOps(ecnId: string, itemId: string): Promise<RoutingOp[]> {
  const { data } = await axiosInstance.get(`/api/v1/ecn/${ecnId}/items/${itemId}/routing`)
  return data
}

export async function createRoutingOp(ecnId: string, itemId: string, body: RoutingOpBody): Promise<RoutingOp> {
  const { data } = await axiosInstance.post(`/api/v1/ecn/${ecnId}/items/${itemId}/routing`, body)
  return data
}

export async function updateRoutingOp(
  ecnId: string,
  itemId: string,
  opId: string,
  body: Partial<Omit<RoutingOpBody, "operation_number">>,
): Promise<RoutingOp> {
  const { data } = await axiosInstance.patch(`/api/v1/ecn/${ecnId}/items/${itemId}/routing/${opId}`, body)
  return data
}

export async function deleteRoutingOp(ecnId: string, itemId: string, opId: string): Promise<void> {
  await axiosInstance.delete(`/api/v1/ecn/${ecnId}/items/${itemId}/routing/${opId}`)
}

// ── MPN management ────────────────────────────────────────────────────────────

export interface MPN {
  id: string
  ecn_item_id: string
  mpn: string
  manufacturer: string | null
  is_default: boolean
  alias_written: boolean
  msl_level: number | null
  lifecycle: "active" | "eol" | "nrnd" | null
  eol_date: string | null
  lead_time_weeks: number | null
  packaging_type: "tape_reel" | "tray" | "tube" | "cut_tape" | null
  do_not_buy: boolean
  alt_mpn: string | null
  notes: string | null
  supplier_data_at: string | null
  created_at: string
}

export interface MPNBody {
  mpn: string
  manufacturer?: string | null
  is_default?: boolean
  msl_level?: number | null
  lifecycle?: string | null
  eol_date?: string | null
  lead_time_weeks?: number | null
  packaging_type?: string | null
  do_not_buy?: boolean
  alt_mpn?: string | null
  notes?: string | null
}

export async function fetchMPNs(ecnId: string, itemId: string): Promise<MPN[]> {
  const { data } = await axiosInstance.get(`/api/v1/ecn/${ecnId}/items/${itemId}`)
  return (data.mpns ?? []) as MPN[]
}

export async function createMPN(ecnId: string, itemId: string, body: MPNBody): Promise<MPN> {
  const { data } = await axiosInstance.post(`/api/v1/ecn/${ecnId}/items/${itemId}/mpns`, body)
  return data
}

export async function updateMPN(
  ecnId: string,
  itemId: string,
  mpnId: string,
  body: Partial<MPNBody>,
): Promise<MPN> {
  const { data } = await axiosInstance.patch(`/api/v1/ecn/${ecnId}/items/${itemId}/mpns/${mpnId}`, body)
  return data
}

export async function deleteMPN(ecnId: string, itemId: string, mpnId: string): Promise<void> {
  await axiosInstance.delete(`/api/v1/ecn/${ecnId}/items/${itemId}/mpns/${mpnId}`)
}

// ── Customer role defaults (SE/PM per customer, admin) ─────────────────────────

export interface CustomerRoleDefault {
  id: string
  cuno: string
  customer_name: string | null
  role_id: "SE" | "PM"
  username: string
  display_name: string | null
  email: string | null
  is_default: boolean
  source: "manual" | "stargile_import"
  is_active: boolean
  added_by: string | null
  added_at: string
  notes: string | null
}

export async function fetchCustomerRoleDefaults(params?: {
  cuno?: string
  role_id?: string
}): Promise<CustomerRoleDefault[]> {
  const { data } = await axiosInstance.get("/api/v1/admin/customer-role-defaults", { params })
  return data
}

export async function addCustomerRoleDefault(body: {
  cuno: string
  role_id: string
  username: string
  customer_name?: string
  display_name?: string
  email?: string
  is_default?: boolean
  notes?: string
}): Promise<CustomerRoleDefault> {
  const { data } = await axiosInstance.post("/api/v1/admin/customer-role-defaults", body)
  return data
}

export async function setCustomerRoleDefault(
  id: string,
  cuno: string,
  roleId: string,
): Promise<CustomerRoleDefault> {
  const { data } = await axiosInstance.patch(
    `/api/v1/admin/customer-role-defaults/${id}/default`,
    null,
    { params: { cuno, role_id: roleId } },
  )
  return data
}

export async function removeCustomerRoleDefault(id: string): Promise<void> {
  await axiosInstance.delete(`/api/v1/admin/customer-role-defaults/${id}`)
}

// ── Movex outbox recovery (admin, S9-4) ─────────────────────────────────────────

export interface MovexOutboxEntry {
  id: string
  ecn_id: string
  ecn_number: string
  facility: string
  ecn_item_id: string | null
  mi_transaction: string
  state: "pending" | "processing" | "completed" | "failed" | "abandoned"
  attempt_count: number
  max_attempts: number
  next_retry_at: string | null
  last_error: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

export async function fetchMovexOutbox(params?: {
  state?: string
  facility?: string
}): Promise<MovexOutboxEntry[]> {
  const { data } = await axiosInstance.get("/api/v1/admin/movex-outbox", { params })
  return data
}

export async function retryMovexOutboxEntry(id: string): Promise<MovexOutboxEntry> {
  const { data } = await axiosInstance.post(`/api/v1/admin/movex-outbox/${id}/retry`)
  return data
}
