import axiosInstance from "@/api/axios"

// ── Compare (Slice D, ADR-012 D5) ────────────────────────────────────────────

export type CompareSideType = "erp" | "snapshot"

export interface CompareSideDescriptor {
  type: CompareSideType
  item_number?: string
  facility?: string
  structure_type?: string
  snapshot_id?: string
}

export interface CompareOptionsBody {
  key?: string[] | null
  fields?: string[] | null
}

export interface FieldChange {
  field: string
  old_value: unknown
  new_value: unknown
}

export interface ChangedLine {
  key: unknown[]
  left: Record<string, unknown>
  right: Record<string, unknown>
  field_changes: FieldChange[]
}

export interface UnresolvedLine {
  side: "left" | "right"
  line: Record<string, unknown>
  reason: string
}

export interface BOMDiffStats {
  left_count: number
  right_count: number
  added_count: number
  removed_count: number
  changed_count: number
  unresolved_count: number
}

export interface BOMDiffResult {
  added: Record<string, unknown>[]
  removed: Record<string, unknown>[]
  changed: ChangedLine[]
  unresolved: UnresolvedLine[]
  stats: BOMDiffStats
}

export interface BOMComparison {
  id: string
  left_descriptor: Record<string, unknown>
  right_descriptor: Record<string, unknown>
  comparison_result: BOMDiffResult
  cost_impact: number | null
  risk_flags: string[]
  created_by: string
  created_at: string
}

export async function postCompare(
  left: CompareSideDescriptor,
  right: CompareSideDescriptor,
  options: CompareOptionsBody = {},
): Promise<BOMComparison> {
  const { data } = await axiosInstance.post("/api/v1/bom/compare", { left, right, options })
  return data as BOMComparison
}

export async function fetchComparison(comparisonId: string): Promise<BOMComparison> {
  const { data } = await axiosInstance.get(`/api/v1/bom/comparisons/${comparisonId}`)
  return data as BOMComparison
}

export async function uploadCompare(
  file: File,
  itemNumber: string,
  facility = "D",
): Promise<BOMComparison> {
  const form = new FormData()
  form.append("file", file)
  form.append("item_number", itemNumber)
  form.append("facility", facility)
  const { data } = await axiosInstance.post("/api/v1/bom/compare/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  })
  return data as BOMComparison
}

export function exportComparisonUrl(comparisonId: string): string {
  return `/api/v1/bom/comparisons/${comparisonId}/export`
}

/** Every field name present on either side of a comparison result — feeds
 * the dynamic key selector and the per-field toggle list (D5: one unified
 * toggle, not PLM's Options-modal/column-click split). */
export function commonFieldNames(result: BOMDiffResult): string[] {
  const names = new Set<string>()
  for (const line of [...result.added, ...result.removed]) {
    Object.keys(line).forEach((k) => names.add(k))
  }
  for (const changed of result.changed) {
    Object.keys(changed.left).forEach((k) => names.add(k))
    Object.keys(changed.right).forEach((k) => names.add(k))
  }
  return Array.from(names).sort()
}
