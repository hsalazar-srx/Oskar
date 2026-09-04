/**
 * Reference-designator (circuit-ref) parsing.
 *
 * Range notation — `R1-R5` expands to R1,R2,R3,R4,R5. This mirrors Stargile's
 * ZECNCIRF.CRZCIRRF, a comma-delimited CLOB supporting ranges
 * (ai/memory/05-stargile-ecn-reference.md:167). movex-rest-api's C-1 endpoint
 * does the same expansion server-side when backfilling, so an author typing
 * `R1-R5` gets the same stored result as a migrated row. Values are stored
 * expanded, matching bom_circuit_refs.
 *
 * Lives outside chip-input.tsx so it can be unit-tested without React and so
 * that file exports only its component (react-refresh/only-export-components).
 */

/** Guards against a typo like R1-R99999 turning into 99k designators. */
const MAX_RANGE_SPAN = 512

const RANGE_RE = /^([A-Za-z]+)(\d+)\s*-\s*([A-Za-z]*)(\d+)$/

/**
 * Expand a single token if it is a numeric-suffix range, else return it as-is.
 *
 * Only expands when both ends share a prefix and the range ascends within
 * MAX_RANGE_SPAN. "R1-C5" is not a contiguous run, and "LF1-A2" is a single
 * designator that happens to contain a hyphen — both are kept verbatim.
 */
export function expandRange(token: string): string[] {
  const m = RANGE_RE.exec(token.trim())
  if (!m) return [token.trim()]

  const [, prefix, startStr, endPrefix, endStr] = m
  if (endPrefix && endPrefix.toUpperCase() !== prefix.toUpperCase()) {
    return [token.trim()]
  }

  const start = parseInt(startStr, 10)
  const end = parseInt(endStr, 10)
  if (end < start || end - start > MAX_RANGE_SPAN) return [token.trim()]

  const out: string[] = []
  for (let i = start; i <= end; i++) out.push(`${prefix}${i}`)
  return out
}

/** Split on comma/whitespace, expand ranges, trim, drop blanks, de-dupe. */
export function parseDesignators(raw: string): string[] {
  const tokens = raw.split(/[,\s]+/).filter(Boolean)
  const expanded = tokens.flatMap(expandRange)
  return Array.from(new Set(expanded.map((t) => t.trim()).filter(Boolean)))
}
