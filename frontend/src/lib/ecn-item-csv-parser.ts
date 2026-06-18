/**
 * Parses an xlsx or csv WorkBook (from SheetJS) into structured ECN item rows.
 *
 * Design decisions from the LLM council (2026-06-17):
 * - All cells read as raw strings ({raw: false}) — never coerce to numbers.
 *   This preserves leading zeros in MOVEX item numbers (e.g. "0034567").
 * - Header detection is by name match, not row position — robust to template evolution.
 * - Header fingerprint check runs before any row parsing and fails fast on mismatch.
 * - Instruction/blank rows skipped by checking whether item_number is empty,
 *   not by hard-coded row index.
 *
 * Required fields (upload blocked if any are blank on any row):
 *   Item No, Item Name, Item Status, Procurement Group, Product Group,
 *   Order Type, Lead Free Code, Good Receiving Method
 *
 * Storage mapping:
 *   item_status              → ecn_items.item_status
 *   order_type               → ecn_items.questionnaire_data.order_type
 *   lead_free_code           → ecn_items.questionnaire_data.lead_free_code
 *   good_receiving_method    → ecn_items.questionnaire_data.good_receiving_method
 *
 * Truncation policy:
 *   item_name > 30 chars is truncated to 30 and flagged as a WARNING (not an error).
 *   The full original name is preserved in warnings[] for display. All other fields
 *   that exceed their max length remain hard errors.
 */

import * as XLSX from "xlsx"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ParsedItemRow {
  /** Original 1-based data row number (after header) */
  rowIndex: number
  is_new_item: boolean
  item_number: string
  item_status: string
  item_name: string | null
  /** Original item_name before truncation — set only when item_name was truncated */
  item_name_original: string | null
  description_2: string | null
  drawing_number: string | null
  procurement_group: string | null
  product_group: string | null
  item_group: string | null
  unit_of_measure: string | null
  customer_alias: string | null
  order_type: string | null
  lead_free_code: string | null
  good_receiving_method: string | null
  effectivity_type: "IMMEDIATE" | "DATE" | "ECN"
  /** Hard errors — row is blocked from import if non-empty */
  errors: string[]
  /** Soft warnings — row is importable but user should review */
  warnings: string[]
}

export interface ParseResult {
  rows: ParsedItemRow[]
  /** Rows skipped because item_number was blank (instruction / example rows) */
  skippedRows: number
  /**
   * Missing required column names — non-empty means the wrong template was uploaded.
   * When this is non-empty, rows will be empty and parsing was aborted early.
   */
  missingColumns: string[]
}

// ---------------------------------------------------------------------------
// Constants — must stay in sync with backend _REQUIRED_COLUMNS and BulkItemRow
// ---------------------------------------------------------------------------

/** All columns that must be present (non-blank) in every data row */
const REQUIRED_COLUMNS: readonly string[] = [
  "Item No",
  "Item Name",
  "Item Status",
  "Procurement Group",
  "Product Group",
  "Order Type",
  "Lead Free Code",
  "Good Receiving Method",
]

/** Max character lengths mirroring backend Pydantic constraints */
const MAX_LENGTHS: Record<string, number> = {
  item_number: 15,
  item_name: 30,
  item_status: 2,
  description_2: 60,
  drawing_number: 20,
  procurement_group: 3,
  product_group: 5,
  item_group: 4,
  unit_of_measure: 3,
  customer_alias: 30,
  order_type: 10,
  lead_free_code: 10,
  good_receiving_method: 10,
}

const EFFECTIVITY_VALUES = new Set<string>(["IMMEDIATE", "DATE", "ECN"])

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function normaliseHeader(h: string): string {
  return h.trim().toLowerCase()
}

function coerceBool(raw: string | null | undefined): boolean {
  if (!raw) return false
  return ["1", "true", "yes", "1.0"].includes(raw.trim().toLowerCase())
}

function trimOrNull(s: string | null | undefined): string | null {
  if (s == null) return null
  const t = String(s).trim()
  return t.length > 0 ? t : null
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

/**
 * Parse a SheetJS Workbook into structured rows.
 *
 * Usage:
 *   const wb = XLSX.read(arrayBuffer, { type: "array", raw: false })
 *   const result = parseWorkbook(wb, ecn.customer_number ?? undefined)
 */
export function parseWorkbook(wb: XLSX.WorkBook, customerNumber?: string): ParseResult {
  const ws = wb.Sheets[wb.SheetNames[0]]
  if (!ws) {
    return { rows: [], skippedRows: 0, missingColumns: [...REQUIRED_COLUMNS] }
  }

  // Convert to array-of-arrays. raw:false ensures all values come back as strings.
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
  const rows: ParsedItemRow[] = []
  let skippedRows = 0

  for (let offset = 0; offset < dataRows.length; offset++) {
    const rawRow = dataRows[offset]
    const rowIndex = offset + 1

    // Skip completely blank rows
    if (!rawRow || !rawRow.some((c) => c != null && String(c).trim().length > 0)) {
      skippedRows++
      continue
    }

    // Skip instruction/example rows — identified by blank item_number
    const rawItemNo = cell(rawRow, "Item No")
    if (!rawItemNo) {
      skippedRows++
      continue
    }

    const errors: string[] = []
    const warnings: string[] = []

    // Map all columns
    const item_number = rawItemNo
    const item_status = trimOrNull(cell(rawRow, "Item Status")) ?? ""

    // item_name — truncate to 30 chars with a warning rather than blocking
    const rawItemName = trimOrNull(cell(rawRow, "Item Name"))
    const itemNameMax = MAX_LENGTHS.item_name
    let item_name: string | null = rawItemName
    let item_name_original: string | null = null
    if (rawItemName && rawItemName.length > itemNameMax) {
      item_name_original = rawItemName
      item_name = rawItemName.slice(0, itemNameMax)
      warnings.push(
        `Item Name truncated to ${itemNameMax} chars (MOVEX limit). Original: "${rawItemName}"`
      )
    }

    const description_2 = trimOrNull(cell(rawRow, "Item Description"))
    const drawing_number = trimOrNull(cell(rawRow, "Drawing No"))
    const procurement_group = trimOrNull(cell(rawRow, "Procurement Group"))
    const product_group = trimOrNull(cell(rawRow, "Product Group"))
    const rawItemGroup = trimOrNull(cell(rawRow, "Item Group"))
    const item_group = rawItemGroup && /^[xXnN]+$/.test(rawItemGroup)
      ? (customerNumber ?? null)
      : rawItemGroup
    const unit_of_measure = trimOrNull(cell(rawRow, "Unit Of Measurement"))
    const customer_alias = trimOrNull(cell(rawRow, "Customer Alias"))
    const order_type = trimOrNull(cell(rawRow, "Order Type"))
    const lead_free_code = trimOrNull(cell(rawRow, "Lead Free Code"))
    const good_receiving_method = trimOrNull(cell(rawRow, "Good Receiving Method"))
    const is_new_item = coerceBool(cell(rawRow, "Is New Item"))
    const effectivity_raw = (trimOrNull(cell(rawRow, "Effectivity Type")) ?? "IMMEDIATE").toUpperCase()
    const effectivity_type: "IMMEDIATE" | "DATE" | "ECN" = EFFECTIVITY_VALUES.has(effectivity_raw)
      ? (effectivity_raw as "IMMEDIATE" | "DATE" | "ECN")
      : "IMMEDIATE"

    // -- Required field presence check --------------------------------------
    const requiredValues: [string, string | null][] = [
      ["item_name", item_name],
      ["item_status", item_status || null],
      ["procurement_group", procurement_group],
      ["product_group", product_group],
      ["order_type", order_type],
      ["lead_free_code", lead_free_code],
      ["good_receiving_method", good_receiving_method],
    ]
    for (const [field, value] of requiredValues) {
      if (!value) errors.push(`${field} is required`)
    }

    // -- Field length validation (item_name excluded — handled above) --------
    const strFields: [string, string | null][] = [
      ["item_number", item_number],
      ["item_status", item_status || null],
      ["description_2", description_2],
      ["drawing_number", drawing_number],
      ["procurement_group", procurement_group],
      ["product_group", product_group],
      ["item_group", item_group],
      ["unit_of_measure", unit_of_measure],
      ["customer_alias", customer_alias],
      ["order_type", order_type],
      ["lead_free_code", lead_free_code],
      ["good_receiving_method", good_receiving_method],
    ]
    for (const [field, value] of strFields) {
      const max = MAX_LENGTHS[field]
      if (value && max && value.length > max) {
        errors.push(`${field} exceeds ${max} characters (got ${value.length})`)
      }
    }

    rows.push({
      rowIndex,
      is_new_item,
      item_number,
      item_status,
      item_name,
      item_name_original,
      description_2,
      drawing_number,
      procurement_group,
      product_group,
      item_group,
      unit_of_measure,
      customer_alias,
      order_type,
      lead_free_code,
      good_receiving_method,
      effectivity_type,
      errors,
      warnings,
    })
  }

  // -- 5. Mark intra-batch duplicate item_numbers as errors -------------------
  const seenNumbers = new Map<string, number>() // item_number → first rowIndex
  for (const row of rows) {
    const num = row.item_number.trim()
    if (!num) continue
    const firstSeen = seenNumbers.get(num)
    if (firstSeen != null) {
      row.errors.push(`Duplicate Item No — also appears at row ${firstSeen}`)
    } else {
      seenNumbers.set(num, row.rowIndex)
    }
  }

  return { rows, skippedRows, missingColumns: [] }
}
