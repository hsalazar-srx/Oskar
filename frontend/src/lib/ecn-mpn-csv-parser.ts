/**
 * Parses an xlsx or csv WorkBook (from SheetJS) into structured bulk MPN rows.
 * Template is the real CAD BOM export shape (see BOM-LI_RFSoC_8X8_GNSS_V2I1.csv),
 * not an invented Oskar-native format — engineers already produce this file
 * from their CAD tool. Mirrors the design of ecn-item-csv-parser.ts (raw string
 * cells, name-based header lookup, header fingerprint check) scoped to this
 * template's own fields.
 *
 * One CSV row expands to 1 or 2 preview rows: Manufacturer 1 Part Number is
 * always the primary/default MPN; Manufacturer 2 Part Number (when present)
 * becomes a second, non-default MPN on the same item.
 *
 * MVP scope: a row with a real component (Manufacturer 1 Part Number present)
 * but no C P/N is a hard ERROR, not a silently-skipped row — auto-resolving
 * those against Movex/DigiKey is a deferred Iteration 2 enhancement (see plan
 * item L). Only fully blank rows (no part at all — CAD export spacer rows)
 * are skipped.
 *
 * Column spec is currently hand-duplicated against the backend's
 * _MPN_UPLOAD_SPEC (ecn_items.py) — see plan item M for tracking a single
 * shared source of truth.
 */

import * as XLSX from "xlsx"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ParsedMpnRow {
  /** 1-based source CSV row number this preview row was expanded from */
  rowIndex: number
  /** true for the Manufacturer 2 half of a row that had both pairs populated */
  isAlternate: boolean
  item_number: string | null
  mpn: string
  manufacturer: string | null
  is_default: boolean
  errors: string[]
  warnings: string[]
}

export interface MpnParseResult {
  rows: ParsedMpnRow[]
  skippedRows: number
  missingColumns: string[]
}

// ---------------------------------------------------------------------------
// Constants — must stay in sync with backend _MPN_UPLOAD_SPEC and BulkMPNRow
// ---------------------------------------------------------------------------

const REQUIRED_COLUMNS: readonly string[] = [
  "C P/N",
  "Manufacturer 1",
  "Manufacturer 1 Part Number",
]

const MAX_LENGTHS: Record<string, number> = {
  item_number: 15,
  mpn: 30,
  manufacturer: 60,
}

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

function validateMpnFields(item_number: string | null, mpn: string, manufacturer: string | null): string[] {
  const errors: string[] = []
  if (!item_number) errors.push("item_number (C P/N) is required — add it via item upload first, then re-upload this MPN sheet")
  else if (item_number.length > MAX_LENGTHS.item_number) errors.push(`item_number exceeds ${MAX_LENGTHS.item_number} characters`)
  if (mpn.length > MAX_LENGTHS.mpn) errors.push(`mpn exceeds ${MAX_LENGTHS.mpn} characters`)
  if (manufacturer && manufacturer.length > MAX_LENGTHS.manufacturer) errors.push(`manufacturer exceeds ${MAX_LENGTHS.manufacturer} characters`)
  return errors
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export function parseMpnWorkbook(wb: XLSX.WorkBook): MpnParseResult {
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

  // -- 4. Parse + expand data rows -------------------------------------------
  const dataRows = aoaRaw.slice(headerRowIdx + 1)
  const rows: ParsedMpnRow[] = []
  let skippedRows = 0

  for (let offset = 0; offset < dataRows.length; offset++) {
    const rawRow = dataRows[offset]
    const rowIndex = offset + 1

    if (!rawRow || !rawRow.some((c) => c != null && String(c).trim().length > 0)) {
      skippedRows++
      continue
    }

    const mpn1 = trimOrNull(cell(rawRow, "Manufacturer 1 Part Number"))
    // A row with no Manufacturer 1 Part Number at all has no component on it —
    // pure CAD-export spacer/filler row. Skip it, same convention as the
    // backend's row_key_field="mpn_1".
    if (!mpn1) {
      skippedRows++
      continue
    }

    const item_number = trimOrNull(cell(rawRow, "C P/N"))
    const manufacturer1 = trimOrNull(cell(rawRow, "Manufacturer 1"))
    const manufacturer2 = trimOrNull(cell(rawRow, "Manufacturer 2"))
    const mpn2 = trimOrNull(cell(rawRow, "Manufacturer 2 Part Number"))

    rows.push({
      rowIndex,
      isAlternate: false,
      item_number,
      mpn: mpn1,
      manufacturer: manufacturer1,
      is_default: true,
      errors: validateMpnFields(item_number, mpn1, manufacturer1),
      warnings: [],
    })

    if (mpn2 && manufacturer2) {
      rows.push({
        rowIndex,
        isAlternate: true,
        item_number,
        mpn: mpn2,
        manufacturer: manufacturer2,
        is_default: false,
        errors: validateMpnFields(item_number, mpn2, manufacturer2),
        warnings: [],
      })
    }
  }

  // -- 5. Mark intra-batch duplicate (item_number, mpn) pairs -----------------
  const seenPairs = new Map<string, number>()
  for (const row of rows) {
    if (!row.item_number) continue
    const key = `${row.item_number}::${row.mpn}`
    const firstSeen = seenPairs.get(key)
    if (firstSeen != null) {
      row.errors.push(`Duplicate Item No + MPN — also appears at row ${firstSeen}`)
    } else {
      seenPairs.set(key, row.rowIndex)
    }
  }

  return { rows, skippedRows, missingColumns: [] }
}
