import axiosInstance from "@/api/axios"

// ── Single-level browse (Slice A) ──────────────────────────────────────────────

export interface BOMLine {
  sequence_number: number
  component_number: string
  description: string
  operation_number: number
  quantity: number
  unit_of_measure: string
  from_date: number
  to_date: number
  item_type: string | null
  status: string | null
  ref_des: string[] | null
  customer_alias: string | null
}

export interface BOMHead {
  item_number: string
  structure_type: string
  facility: string
  description: string
  lines: BOMLine[]
}

export interface FetchBOMOptions {
  facility?: string
  structureType?: string
  bomType?: string
  effectiveOn?: string
  includeExpired?: boolean
}

export async function fetchBOM(itemNumber: string, opts: FetchBOMOptions = {}): Promise<BOMHead> {
  const params: Record<string, string> = {}
  if (opts.facility) params.facility = opts.facility
  if (opts.structureType) params.structure_type = opts.structureType
  if (opts.bomType) params.bom_type = opts.bomType
  if (opts.effectiveOn) params.effective_on = opts.effectiveOn
  if (opts.includeExpired) params.include_expired = "true"
  const { data } = await axiosInstance.get(`/api/v1/bom/${itemNumber}`, { params })
  return data as BOMHead
}

// ── Multi-level explosion (Slice B) ────────────────────────────────────────────

export interface BOMTreeNode {
  component_number: string
  description: string
  operation_number: number
  quantity: number
  cumulative_quantity: number
  item_type: string | null
  is_phantom: boolean
  children: BOMTreeNode[]
}

export interface FetchBOMIndentedOptions {
  facility?: string
  structureType?: string
  depth?: number
}

export async function fetchBOMIndented(itemNumber: string, opts: FetchBOMIndentedOptions = {}): Promise<BOMTreeNode> {
  const params: Record<string, string> = {}
  if (opts.facility) params.facility = opts.facility
  if (opts.structureType) params.structure_type = opts.structureType
  if (opts.depth) params.depth = String(opts.depth)
  const { data } = await axiosInstance.get(`/api/v1/bom/${itemNumber}/indented`, { params })
  return data as BOMTreeNode
}

// ── Where-used (Slice B) ───────────────────────────────────────────────────────

export interface WhereUsedLine {
  parent_item: string
  structure_type: string
  facility: string
  sequence_number: number
  component_number: string
  operation_number: number
  quantity: number
  unit_of_measure: string
  from_date: number
  to_date: number
}

export interface FetchWhereUsedOptions {
  facility?: string
  effectiveOn?: string
}

export async function fetchWhereUsed(itemNumber: string, opts: FetchWhereUsedOptions = {}): Promise<WhereUsedLine[]> {
  const params: Record<string, string> = {}
  if (opts.facility) params.facility = opts.facility
  if (opts.effectiveOn) params.effective_on = opts.effectiveOn
  const { data } = await axiosInstance.get(`/api/v1/bom/${itemNumber}/where-used`, { params })
  return data as WhereUsedLine[]
}
