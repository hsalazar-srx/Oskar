import axiosInstance from "@/api/axios"

// ── Shared types ──────────────────────────────────────────────────────────────

export interface GroupEntry {
  procurement_group: string
  product_group: string
  commodity_codes: string[]
}

export interface SuggestPnResponse {
  suggested_pn: string
  commodity_code: string
  sequence: number
  prefix: string
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

export async function suggestPn(prgp: string, itcl: string): Promise<SuggestPnResponse> {
  const { data } = await axiosInstance.get(`/api/v1/parts/suggest-pn?prgp=${prgp}&itcl=${itcl}`)
  return data
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
