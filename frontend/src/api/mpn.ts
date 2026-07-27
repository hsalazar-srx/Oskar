import axiosInstance from "@/api/axios"

// ── Types ─────────────────────────────────────────────────────────────────────

export type MpnSearchField = "item" | "mfr" | "mpn"

export interface MpnSearchHit {
  id: string
  item_number: string
  supplier_number: string
  mpn: string
  manufacturer_name: string | null
  manufacturer_canonical: string | null
  is_default: boolean
  end_effective_date: string | null
}

export interface MpnSearchResponse {
  results: MpnSearchHit[]
  total: number
  limit: number
  offset: number
}

// ── API ───────────────────────────────────────────────────────────────────────

export async function searchMpn(params: {
  q: string
  field?: MpnSearchField
  limit?: number
  offset?: number
}): Promise<MpnSearchResponse> {
  const { data } = await axiosInstance.get("/api/v1/mpn/search", {
    params: {
      q: params.q,
      field: params.field ?? "mpn",
      limit: params.limit ?? 50,
      offset: params.offset ?? 0,
    },
  })
  return data as MpnSearchResponse
}
