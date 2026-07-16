/**
 * Parses an xlsx or csv WorkBook (from SheetJS) into structured bulk routing
 * operation rows. Mirrors the design of ecn-item-csv-parser.ts (LLM council
 * 2026-06-17 decisions: raw string cells, name-based header lookup, header
 * fingerprint check before row parsing, blank-Item-No rows are instruction
 * rows and are skipped) but scoped to the routing template's own fields.
 *
 * Unlike the item template, rows are NOT required to share one Item No — one
 * upload can carry a single item's full routing (many operation numbers,
 * one item) or many items' routing changes at once. The only uniqueness
 * constraint is on the (Item No, Operation No) pair.
 *
 * Required fields (upload blocked if any are blank on any row):
 *   Item No, Operation No, Operation Description, Work Centre, Run Time, Change Type
 *
 * Column spec is currently hand-duplicated against the backend's
 * _ROUTING_UPLOAD_SPEC (ecn_routing.py) — see plan item M for tracking a
 * single shared source of truth.
 */

import * as XLSX from "xlsx"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ParsedRoutingRow {
  rowIndex: number
  item_number: string
  operation_number: string
  operation_description: string | null
  work_centre: string | null
  run_time: string | null
  setup_time: string | null
  change_type: string | null
  errors: string[]
  warnings: string[]
}

export interface RoutingParseResult {
  rows: ParsedRoutingRow[]
  skippedRows: number
  missingColumns: string[]
}

// ---------------------------------------------------------------------------
// Constants — must stay in sync with backend _ROUTING_UPLOAD_SPEC and BulkRoutingRow
// ---------------------------------------------------------------------------

const REQUIRED_COLUMNS: readonly string[] = [
  "Item No",
  "Operation No",
  "Operation Description",
  "Work Centre",
  "Run Time",
  "Change Type",
]

const MAX_LENGTHS: Record<string, number> = {
  item_number: 15,
  operation_description: 30,
  work_centre: 8,
}

const VALID_CHANGE_TYPES = new Set(["ADD", "UPDATE", "DELETE"])

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function normaliseHeader(h: string): string {
  return h.trim().toLowerCase()
}

function trimOrNull(s: string | null | undefined): string | null {
  if (s == null) return null
  const t = String(s).trim()
  return t.length > 0 ? t : null
}

function isNonNegativeNumber(s: string | null): boolean {
  if (s == null) return false
  const n = Number(s)
  return !Number.isNaN(n) && n >= 0
}

function isPositiveInteger(s: string | null): boolean {
  if (s == null) return false
  return /^\d+$/.test(s) && Number(s) >= 1
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export function parseRoutingWorkbook(wb: XLSX.WorkBook): RoutingParseResult {
  const ws = wb.Sheets[wb.SheetNames[0]]
  if (!ws) {
    return { rows: [], skippedRows: 0, missingColumns: [...REQUIRED_COLUMNS] }
  }

  const aoaRaw: (string | null)[][] = XLSX.utils.sheet_to_json(ws, {
    header: 1,
    raw: false,
    defval: null,
  })

  if (aoaRaw.length === 0) {
    return { rows: [], skippedRows: 0, missingColumns: [...REQUIRED_COLUMNS] }
  }

  // -- 1. Locate header row (first non-blank row) ----------------------------
  let headerRowIdx = -1
  let rawHeaders: string[] = []
  for (let i = 0; i < aoaRaw.length; i++) {
    const candidates = (aoaRaw[i] ?? []).map((c) => (c != null ? String(c).trim() : ""))
    if (candidates.some((c) => c.length > 0)) {
      headerRowIdx = i
      rawHeaders = candidates
      break
    }
  }
  if (headerRowIdx === -1) {
    return { rows: [], skippedRows: 0, missingColumns: [...REQUIRED_COLUMNS] }
  }

  // -- 2. Header fingerprint check ------------------------------------------
  const normHeaders = new Set(rawHeaders.map(normaliseHeader))
  const missingColumns = REQUIRED_COLUMNS.filter(
    (col) => !normHeaders.has(normaliseHeader(col))
  )
  if (missingColumns.length > 0) {
    return { rows: [], skippedRows: 0, missingColumns }
  }

  // -- 3. Build header→column-index map -------------------------------------
  const headerIndex: Record<string, number> = {}
  rawHeaders.forEach((h, i) => {
    if (h) headerIndex[normaliseHeader(h)] = i
  })

  function cell(row: (string | null)[], colName: string): string | null {
    const idx = headerIndex[normaliseHeader(colName)]
    if (idx == null) return null
    const v = row[idx]
    return v != null ? String(v).trim() : null
  }

  // -- 4. Parse data rows ---------------------------------------------------
  const dataRows = aoaRaw.slice(headerRowIdx + 1)
  const rows: ParsedRoutingRow[] = []
  let skippedRows = 0

  for (let offset = 0; offset < dataRows.length; offset++) {
    const rawRow = dataRows[offset]
    const rowIndex = offset + 1

    if (!rawRow || !rawRow.some((c) => c != null && String(c).trim().length > 0)) {
      skippedRows++
      continue
    }

    const item_number = trimOrNull(cell(rawRow, "Item No"))
    if (!item_number) {
      skippedRows++
      continue
    }

    const errors: string[] = []
    const warnings: string[] = []

    const operation_number = trimOrNull(cell(rawRow, "Operation No")) ?? ""
    const operation_description = trimOrNull(cell(rawRow, "Operation Description"))
    const work_centre = trimOrNull(cell(rawRow, "Work Centre")) ?? trimOrNull(cell(rawRow, "Work Center"))
    const run_time = trimOrNull(cell(rawRow, "Run Time"))
    const setup_time = trimOrNull(cell(rawRow, "Setup Time"))
    const change_type = trimOrNull(cell(rawRow, "Change Type"))?.toUpperCase() ?? null

    if (!operation_number) errors.push("operation_number is required")
    else if (!isPositiveInteger(operation_number)) errors.push("operation_number must be a positive integer")

    if (!operation_description) errors.push("operation_description is required")
    else if (operation_description.length > MAX_LENGTHS.operation_description)
      errors.push(`operation_description exceeds ${MAX_LENGTHS.operation_description} characters`)

    if (!work_centre) errors.push("work_centre is required")
    else if (work_centre.length > MAX_LENGTHS.work_centre)
      errors.push(`work_centre exceeds ${MAX_LENGTHS.work_centre} characters`)

    if (!run_time) errors.push("run_time is required")
    else if (!isNonNegativeNumber(run_time)) errors.push("run_time must be a non-negative number")

    if (setup_time && !isNonNegativeNumber(setup_time)) errors.push("setup_time must be a non-negative number")

    if (!change_type) errors.push("change_type is required")
    else if (!VALID_CHANGE_TYPES.has(change_type)) errors.push(`change_type must be one of ${[...VALID_CHANGE_TYPES].join(", ")}`)

    if (item_number.length > MAX_LENGTHS.item_number)
      errors.push(`item_number exceeds ${MAX_LENGTHS.item_number} characters`)

    rows.push({
      rowIndex,
      item_number,
      operation_number,
      operation_description,
      work_centre,
      run_time,
      setup_time,
      change_type,
      errors,
      warnings,
    })
  }

  // -- 5. Mark intra-batch duplicate (item_number, operation_number) pairs --
  const seenPairs = new Map<string, number>()
  for (const row of rows) {
    const key = `${row.item_number}::${row.operation_number}`
    const firstSeen = seenPairs.get(key)
    if (firstSeen != null) {
      row.errors.push(`Duplicate Item No + Operation No — also appears at row ${firstSeen}`)
    } else {
      seenPairs.set(key, row.rowIndex)
    }
  }

  return { rows, skippedRows, missingColumns: [] }
}
