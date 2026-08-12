/**
 * Parses an xlsx or csv WorkBook (from SheetJS) into structured bulk
 * BOM-change rows. Mirrors ecn-routing-csv-parser.ts's design (raw string
 * cells, name-based header lookup, header fingerprint check before row
 * parsing, blank-Item-No rows are instruction rows and are skipped).
 *
 * Multi-item, ECN-wide, same as the routing template — one upload can carry
 * a single item's full BOM-change set or many items' changes at once. The
 * only uniqueness constraint is on the (Item No, Component Number,
 * Operation No) triple, matching the backend's bulk_create_bom_changes
 * dup-check.
 *
 * Required fields (upload blocked if any are blank on any row):
 *   Item No, Component Number, Change Type
 * CHANGE/DELETE additionally require Old From Date — enforced service-side
 * (not by Pydantic, see BulkBomChangeRow's docstring in ecn_schemas.py) so
 * this mirrors that same choice client-side for instant feedback rather
 * than a round trip.
 *
 * Column spec is currently hand-duplicated against the backend's
 * _BOM_CHANGE_UPLOAD_SPEC (ecn_bom.py) — same pre-existing gap
 * ecn-routing-csv-parser.ts and ecn-item-csv-parser.ts already have.
 */

import * as XLSX from "xlsx"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ParsedBomChangeRow {
  rowIndex: number
  item_number: string
  component_number: string
  change_type: string | null
  quantity: string | null
  unit_of_measure: string | null
  operation_number: string | null
  sequence_number: string | null
  from_date: string | null
  old_from_date: string | null
  old_quantity: string | null
  circuit_refs_new: string | null
  notes: string | null
  errors: string[]
  warnings: string[]
}

export interface BomChangeParseResult {
  rows: ParsedBomChangeRow[]
  skippedRows: number
  missingColumns: string[]
}

// ---------------------------------------------------------------------------
// Constants — must stay in sync with backend _BOM_CHANGE_UPLOAD_SPEC and BulkBomChangeRow
// ---------------------------------------------------------------------------

const REQUIRED_COLUMNS: readonly string[] = [
  "Item No",
  "Component Number",
  "Change Type",
]

const MAX_LENGTHS: Record<string, number> = {
  item_number: 15,
  component_number: 15,
  unit_of_measure: 3,
}

const VALID_CHANGE_TYPES = new Set(["ADD", "CHANGE", "DELETE"])

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

function isYyyymmdd(s: string | null): boolean {
  if (s == null) return false
  return /^\d{8}$/.test(s)
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export function parseBomChangeWorkbook(wb: XLSX.WorkBook): BomChangeParseResult {
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
  const rows: ParsedBomChangeRow[] = []
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

    const component_number = trimOrNull(cell(rawRow, "Component Number"))
    const change_type = trimOrNull(cell(rawRow, "Change Type"))?.toUpperCase() ?? null
    const quantity = trimOrNull(cell(rawRow, "Quantity"))
    const unit_of_measure = trimOrNull(cell(rawRow, "Unit of Measure"))
    const operation_number = trimOrNull(cell(rawRow, "Operation Number"))
    const sequence_number = trimOrNull(cell(rawRow, "Sequence Number"))
    const from_date = trimOrNull(cell(rawRow, "From Date"))
    const old_from_date = trimOrNull(cell(rawRow, "Old From Date"))
    const old_quantity = trimOrNull(cell(rawRow, "Old Quantity"))
    const circuit_refs_new = trimOrNull(cell(rawRow, "Circuit Reference"))
    const notes = trimOrNull(cell(rawRow, "Notes"))

    if (!component_number) errors.push("component_number is required")
    else if (component_number.length > MAX_LENGTHS.component_number)
      errors.push(`component_number exceeds ${MAX_LENGTHS.component_number} characters`)

    if (!change_type) errors.push("change_type is required")
    else if (!VALID_CHANGE_TYPES.has(change_type))
      errors.push(`change_type must be one of ${[...VALID_CHANGE_TYPES].join(", ")}`)
    else if ((change_type === "CHANGE" || change_type === "DELETE") && !old_from_date)
      errors.push(`old_from_date is required for change_type ${change_type}`)

    if (quantity && !isNonNegativeNumber(quantity)) errors.push("quantity must be a non-negative number")
    if (old_quantity && !isNonNegativeNumber(old_quantity)) errors.push("old_quantity must be a non-negative number")
    if (operation_number && !isPositiveInteger(operation_number)) errors.push("operation_number must be a positive integer")
    if (sequence_number && !isPositiveInteger(sequence_number)) errors.push("sequence_number must be a positive integer")
    if (from_date && !isYyyymmdd(from_date)) errors.push("from_date must be YYYYMMDD")
    if (old_from_date && !isYyyymmdd(old_from_date)) errors.push("old_from_date must be YYYYMMDD")

    if (unit_of_measure && unit_of_measure.length > MAX_LENGTHS.unit_of_measure)
      errors.push(`unit_of_measure exceeds ${MAX_LENGTHS.unit_of_measure} characters`)
    if (item_number.length > MAX_LENGTHS.item_number)
      errors.push(`item_number exceeds ${MAX_LENGTHS.item_number} characters`)

    rows.push({
      rowIndex,
      item_number,
      component_number: component_number ?? "",
      change_type,
      quantity,
      unit_of_measure,
      operation_number,
      sequence_number,
      from_date,
      old_from_date,
      old_quantity,
      circuit_refs_new,
      notes,
      errors,
      warnings,
    })
  }

  // -- 5. Mark intra-batch duplicate (item_number, component_number, operation_number) triples --
  const seenTriples = new Map<string, number>()
  for (const row of rows) {
    const key = `${row.item_number}::${row.component_number}::${row.operation_number ?? ""}`
    const firstSeen = seenTriples.get(key)
    if (firstSeen != null) {
      row.errors.push(
        `Duplicate Item No + Component Number + Operation No — also appears at row ${firstSeen}`
      )
    } else {
      seenTriples.set(key, row.rowIndex)
    }
  }

  return { rows, skippedRows, missingColumns: [] }
}
