import { useMemo, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { useMutation, useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useAuthStore } from "@/store/auth"
import {
  postCompare, fetchComparison, uploadCompare, exportComparisonUrl, commonFieldNames,
  type CompareSideDescriptor, type BOMComparison, type ChangedLine,
} from "@/api/bomCompare"

type SourceMode = "erp" | "upload"

interface SidePickerState {
  mode: SourceMode
  itemNumber: string
  facility: string
  file: File | null
}

function emptySide(): SidePickerState {
  return { mode: "erp", itemNumber: "", facility: "D", file: null }
}

/**
 * Slice D — BOM comparison engine UI (ADR-012 D5).
 *
 * Old/New source pickers: live ERP item (by item number — a full Movex
 * BOM-finder search-by-customer/product dialog is a documented gap here,
 * see the module-level note below) or file upload. Saved snapshot as a
 * pickable source is like-wise deferred (no snapshot browse/list UI exists
 * yet in any slice) — the backend (GET/POST /bom/compare, snapshot
 * descriptor type) already supports it; this page only wires the two
 * sources it can build a real picker UI for without a snapshot list page.
 *
 * Key selector: dynamic, built from commonFieldNames() over the comparison
 * RESULT (available after the first compare runs) rather than pre-flight
 * introspection of both sides — matches PLM's own behaviour of only being
 * able to pick a key from fields actually present in the loaded data.
 * Before the first compare, the default ERP-vs-ERP key
 * (component_number, operation_number) is used, matching compare.py's own
 * default.
 *
 * One per-field toggle (D5): a single checkbox list controls both which
 * fields are included in the (re-run) diff AND which are shown in the
 * table — no separate Options-modal/column-click split.
 *
 * Save + history: every compare call persists automatically server-side
 * (POST /bom/compare -> insert_comparison, migration 0027) and the result's
 * id is written to the URL (?id=...), making any comparison bookmarkable/
 * shareable/reloadable via fetchComparison — that IS this slice's save/
 * history mechanism. A dedicated "history list" page (browse past
 * comparisons by date/user) is a documented gap: it needs a
 * GET /bom/comparisons (list) endpoint that was not in this slice's router
 * scope (only GET .../{id} was specified) and has no page of its own here.
 */
export default function BOMComparePage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const user = useAuthStore((s) => s.user)

  const comparisonId = searchParams.get("id")
  // Pre-fill from BOMBrowserPage's "Compare against…" launcher button
  // (?left=<item>&leftFacility=<facility>) — see BOMBrowserPage.tsx.
  const prefillLeftItem = searchParams.get("left")
  const prefillLeftFacility = searchParams.get("leftFacility")

  const [left, setLeft] = useState<SidePickerState>(() =>
    prefillLeftItem
      ? { ...emptySide(), itemNumber: prefillLeftItem, facility: prefillLeftFacility ?? "D" }
      : emptySide(),
  )
  const [right, setRight] = useState<SidePickerState>(emptySide())
  const [keyFields, setKeyFields] = useState<string[]>(["component_number", "operation_number"])
  const [enabledFields, setEnabledFields] = useState<Set<string> | null>(null) // null = all fields

  const comparisonQuery = useQuery<BOMComparison>({
    queryKey: ["bom-comparison", comparisonId],
    queryFn: () => fetchComparison(comparisonId!),
    enabled: !!comparisonId,
    retry: 1,
  })

  const compareMutation = useMutation({
    mutationFn: async () => {
      if (left.mode === "upload") {
        if (!left.file) throw new Error("Select a file for the Old side.")
        return uploadCompare(left.file, right.itemNumber.trim().toUpperCase(), right.facility)
      }
      const leftDescriptor: CompareSideDescriptor = {
        type: "erp", item_number: left.itemNumber.trim().toUpperCase(), facility: left.facility,
      }
      const rightDescriptor: CompareSideDescriptor = {
        type: "erp", item_number: right.itemNumber.trim().toUpperCase(), facility: right.facility,
      }
      const fieldsList = enabledFields ? Array.from(enabledFields) : null
      return postCompare(leftDescriptor, rightDescriptor, { key: keyFields, fields: fieldsList })
    },
    onSuccess: (comparison) => {
      setSearchParams({ id: comparison.id })
    },
  })

  const comparison = compareMutation.data ?? comparisonQuery.data

  const fieldOptions = useMemo(
    () => (comparison ? commonFieldNames(comparison.comparison_result) : []),
    [comparison],
  )

  function toggleField(field: string) {
    setEnabledFields((prev) => {
      const base = prev ?? new Set(fieldOptions)
      const next = new Set(base)
      if (next.has(field)) next.delete(field)
      else next.add(field)
      return next
    })
  }

  function canSubmit(): boolean {
    if (left.mode === "upload") return !!left.file && !!right.itemNumber.trim()
    return !!left.itemNumber.trim() && !!right.itemNumber.trim()
  }

  const stats = comparison?.comparison_result.stats

  return (
    <div className="min-h-screen bg-[#f5f7fa] flex flex-col">
      <header className="sticky top-0 z-[1020] border-b border-[#e8ecf0] bg-white shadow-[var(--shadow-xs)] px-6 h-14 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2.5">
          <button onClick={() => navigate("/bom")} className="w-7 h-7 rounded-md bg-[#0066cc] flex items-center justify-center shrink-0">
            <span className="text-white font-bold text-xs">O</span>
          </button>
          <span className="font-semibold tracking-tight text-[#0f172a]">Oskar</span>
          <span className="text-[#d1d9e0]">/</span>
          <span className="text-sm text-[#94a3b8]">BOM Compare</span>
        </div>
        <div className="flex items-center gap-3">
          {user && (
            <span className="text-xs text-[#94a3b8] hidden sm:block">
              <span className="font-medium text-[#475569]">{user.username}</span>
            </span>
          )}
          <button
            onClick={() => navigate("/bom")}
            className="h-9 px-3 rounded-lg border border-[#d1d9e0] bg-white text-sm text-[#475569] hover:bg-[#f5f7fa] transition-colors duration-150"
          >
            Back to BOM Browser
          </button>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-6xl px-6 py-6 space-y-5">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <SidePicker label="Old (left)" state={left} onChange={setLeft} />
          <SidePicker label="New (right)" state={right} onChange={setRight} />
        </div>

        <div className="flex items-center gap-3">
          <label className="text-xs text-[#475569]" htmlFor="compare-key-fields">
            Comparison key
          </label>
          <input
            id="compare-key-fields"
            type="text"
            className="h-9 rounded-lg border border-[#d1d9e0] bg-white px-3 text-sm font-mono w-64"
            value={keyFields.join(",")}
            onChange={(e) => setKeyFields(e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
            aria-label="Comparison key fields"
          />
          <Button
            onClick={() => compareMutation.mutate()}
            disabled={!canSubmit() || compareMutation.isPending}
            size="sm"
          >
            {compareMutation.isPending ? "Comparing…" : "Compare"}
          </Button>
        </div>

        {fieldOptions.length > 0 && (
          <div className="rounded-xl border border-[#e8ecf0] bg-white px-4 py-3">
            <div className="text-xs font-semibold uppercase tracking-wider text-[#94a3b8] mb-2">
              Fields (diff + display — one toggle)
            </div>
            <div className="flex flex-wrap gap-3">
              {fieldOptions.map((field) => (
                <label key={field} className="flex items-center gap-1.5 text-xs text-[#475569] cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={enabledFields ? enabledFields.has(field) : true}
                    onChange={() => toggleField(field)}
                    aria-label={`Toggle field ${field}`}
                  />
                  {field}
                </label>
              ))}
            </div>
          </div>
        )}

        {(compareMutation.isPending || (comparisonId && comparisonQuery.isLoading)) && (
          <div className="flex items-center justify-center py-16">
            <Spinner size="lg" />
          </div>
        )}

        {compareMutation.isError && (
          <div className="flex items-center gap-2.5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {(compareMutation.error as any)?.response?.data?.detail ?? "Compare failed."}
          </div>
        )}

        {comparison && stats && (
          <div className="space-y-4">
            <div className="flex items-center gap-4">
              <SummaryStat label="Differences" value={stats.changed_count} tone="amber" />
              <SummaryStat label="Additions" value={stats.added_count} tone="green" />
              <SummaryStat label="Subtractions" value={stats.removed_count} tone="red" />
              {stats.unresolved_count > 0 && (
                <SummaryStat label="Unresolved" value={stats.unresolved_count} tone="slate" />
              )}
              <a
                href={exportComparisonUrl(comparison.id)}
                className="ml-auto h-9 px-3 rounded-lg border border-[#d1d9e0] bg-white text-sm text-[#475569] hover:bg-[#f5f7fa] transition-colors duration-150 flex items-center"
                download
              >
                Export .xlsx
              </a>
            </div>

            <DiffTable comparison={comparison} />
          </div>
        )}
      </main>
    </div>
  )
}

// ── Side picker (Old/New source: ERP item or file upload) ───────────────────

function SidePicker({
  label, state, onChange,
}: {
  label: string
  state: SidePickerState
  onChange: (next: SidePickerState) => void
}) {
  return (
    <div className="rounded-xl border border-[#e8ecf0] bg-white px-4 py-3 space-y-2">
      <div className="text-xs font-semibold uppercase tracking-wider text-[#94a3b8]">{label}</div>
      <div className="flex gap-2 text-xs">
        <button
          type="button"
          className={`px-2 py-1 rounded-md border ${state.mode === "erp" ? "border-[#0066cc] text-[#0066cc] bg-[#0066cc]/5" : "border-[#d1d9e0] text-[#94a3b8]"}`}
          onClick={() => onChange({ ...state, mode: "erp" })}
        >
          Movex item
        </button>
        <button
          type="button"
          className={`px-2 py-1 rounded-md border ${state.mode === "upload" ? "border-[#0066cc] text-[#0066cc] bg-[#0066cc]/5" : "border-[#d1d9e0] text-[#94a3b8]"}`}
          onClick={() => onChange({ ...state, mode: "upload" })}
        >
          Upload file
        </button>
      </div>
      {state.mode === "erp" ? (
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Item number"
            className="h-9 flex-1 rounded-lg border border-[#d1d9e0] bg-white px-3 text-sm font-mono"
            value={state.itemNumber}
            onChange={(e) => onChange({ ...state, itemNumber: e.target.value })}
            aria-label={`${label} item number`}
          />
          <input
            type="text"
            placeholder="Facility"
            className="h-9 w-20 rounded-lg border border-[#d1d9e0] bg-white px-3 text-sm font-mono"
            value={state.facility}
            onChange={(e) => onChange({ ...state, facility: e.target.value })}
            aria-label={`${label} facility`}
          />
        </div>
      ) : (
        <input
          type="file"
          accept=".xlsx,.csv"
          className="text-sm"
          onChange={(e) => onChange({ ...state, file: e.target.files?.[0] ?? null })}
          aria-label={`${label} file`}
        />
      )}
    </div>
  )
}

// ── Summary stat tile ─────────────────────────────────────────────────────────

const TONE_CLASSES: Record<string, string> = {
  amber: "text-amber-700 bg-amber-50 border-amber-200",
  green: "text-green-700 bg-green-50 border-green-200",
  red: "text-red-700 bg-red-50 border-red-200",
  slate: "text-slate-700 bg-slate-50 border-slate-200",
}

function SummaryStat({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className={`rounded-lg border px-3 py-2 ${TONE_CLASSES[tone]}`}>
      <div className="text-lg font-semibold tabular-nums">{value}</div>
      <div className="text-[10px] uppercase tracking-wider">{label}</div>
    </div>
  )
}

// ── Side-by-side diff table: Old | Changes | New ─────────────────────────────

function lineKeyDisplay(line: Record<string, unknown>): string {
  for (const candidate of ["item_number", "component_number", "ipn"]) {
    if (candidate in line) return String(line[candidate])
  }
  return "—"
}

function DiffTable({ comparison }: { comparison: BOMComparison }) {
  const { added, removed, changed } = comparison.comparison_result

  if (added.length === 0 && removed.length === 0 && changed.length === 0) {
    return (
      <div className="rounded-xl border border-[#e8ecf0] bg-white text-center py-16 text-sm text-[#94a3b8]">
        No differences — the two BOMs match.
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-[#e8ecf0] bg-white overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow className="bg-[#f8fafc] hover:bg-[#f8fafc] border-b border-[#e8ecf0]">
            <TableHead className="w-20 text-xs uppercase tracking-wider text-[#94a3b8] py-3">Status</TableHead>
            <TableHead className="text-xs uppercase tracking-wider text-[#94a3b8] py-3">Key</TableHead>
            <TableHead className="text-xs uppercase tracking-wider text-[#94a3b8] py-3">Old</TableHead>
            <TableHead className="text-xs uppercase tracking-wider text-[#94a3b8] py-3">Changes</TableHead>
            <TableHead className="text-xs uppercase tracking-wider text-[#94a3b8] py-3">New</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {removed.map((line, i) => (
            <TableRow key={`removed-${i}`} className="border-b border-[#f1f5f9] bg-red-50/40">
              <TableCell className="py-2.5 text-xs font-medium text-red-700">Removed</TableCell>
              <TableCell className="py-2.5 font-mono text-xs text-[#0f172a]">{lineKeyDisplay(line)}</TableCell>
              <TableCell className="py-2.5 text-xs text-[#475569]">{JSON.stringify(line)}</TableCell>
              <TableCell className="py-2.5 text-xs text-[#94a3b8]">—</TableCell>
              <TableCell className="py-2.5 text-xs text-[#94a3b8]">—</TableCell>
            </TableRow>
          ))}
          {added.map((line, i) => (
            <TableRow key={`added-${i}`} className="border-b border-[#f1f5f9] bg-green-50/40">
              <TableCell className="py-2.5 text-xs font-medium text-green-700">Added</TableCell>
              <TableCell className="py-2.5 font-mono text-xs text-[#0f172a]">{lineKeyDisplay(line)}</TableCell>
              <TableCell className="py-2.5 text-xs text-[#94a3b8]">—</TableCell>
              <TableCell className="py-2.5 text-xs text-[#94a3b8]">—</TableCell>
              <TableCell className="py-2.5 text-xs text-[#475569]">{JSON.stringify(line)}</TableCell>
            </TableRow>
          ))}
          {changed.map((change: ChangedLine, i) => (
            <TableRow key={`changed-${i}`} className="border-b border-[#f1f5f9] bg-amber-50/40">
              <TableCell className="py-2.5 text-xs font-medium text-amber-700">Changed</TableCell>
              <TableCell className="py-2.5 font-mono text-xs text-[#0f172a]">
                {change.key.map(String).join(" / ")}
              </TableCell>
              <TableCell className="py-2.5 text-xs text-[#475569]">
                {change.field_changes.map((fc) => (
                  <div key={fc.field}>{fc.field}: {String(fc.old_value)}</div>
                ))}
              </TableCell>
              <TableCell className="py-2.5 text-xs text-amber-700">
                {change.field_changes.map((fc) => (
                  <div key={fc.field}>{fc.field}</div>
                ))}
              </TableCell>
              <TableCell className="py-2.5 text-xs text-[#475569]">
                {change.field_changes.map((fc) => (
                  <div key={fc.field}>{fc.field}: {String(fc.new_value)}</div>
                ))}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
