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
  return data as { id: string; item_number: string; item_name: string; is_new_item: boolean }[]
}

export async function fireTransition(
  ecnId: string,
  trigger: string,
  actorRole: string,
  updatedAt: string,
  extra?: Record<string, string>,
) {
  const { data } = await axiosInstance.patch(
    `/api/v1/ecn/${ecnId}/status`,
    { trigger, actor_role: actorRole, ...extra },
    { headers: { "If-Unmodified-Since": updatedAt } },
  )
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
