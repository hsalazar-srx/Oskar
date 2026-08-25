import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Spinner } from "@/components/ui/spinner"
import { createEcnScopedBomChange, type BOMChangeBody } from "@/api/ecn"
import { fetchBOM, type BOMHead, type BOMLine } from "@/api/bom"

/**
 * ADR-014 — add a BOM change from the ECN-wide BOM Changes tab, with no item
 * on the ECN required.
 *
 * Before ADR-014 a BOM change could only be authored through an ecn_items row
 * (ecn_bom_changes.ecn_item_id was NOT NULL), so an ECN that revises only a
 * structure had to carry a dummy item row that told reviewers the item master
 * was changing when it was not. Stargile never worked this way: its ZECNBOMS
 * rows carry their own parent (BMPRNO) and have no link to the items table.
 *
 * The BOM browser here is the "browse by item number" scope of I2-15: type a
 * parent number, see its live Movex structure, click a line to author a
 * CHANGE/DELETE against it (old values prefilled from the real line, which is
 * what makes old_from_date correct — it must identify the live MPDMAT line),
 * or add a new component to it. A search-as-you-type item finder is still the
 * open half of I2-15 and needs a backend route first (the adapter has
 * search_items; no route exposes it).
 */

const CHANGE_TYPES = ["ADD", "CHANGE", "DELETE"] as const
type ChangeType = (typeof CHANGE_TYPES)[number]

const CHANGE_TYPE_LABEL: Record<ChangeType, string> = {
  ADD: "Add component",
  CHANGE: "Change existing",
  DELETE: "Remove component",
}

function fmtDate(yyyymmdd: number): string {
  if (!yyyymmdd || yyyymmdd >= 99999999) return "—"
  const s = String(yyyymmdd)
  return s.length === 8 ? `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}` : s
}

interface FormState {
  parent_item_number: string
  change_type: ChangeType
  component_number: string
  quantity: string
  unit_of_measure: string
  operation_number: string
  sequence_number: string
  from_date: string
  old_from_date: string
  old_quantity: string
  old_operation_number: string
  circuit_refs_new: string
}

const EMPTY_FORM: FormState = {
  parent_item_number: "",
  change_type: "ADD",
  component_number: "",
  quantity: "",
  unit_of_measure: "EA",
  operation_number: "",
  sequence_number: "",
  from_date: "",
  old_from_date: "",
  old_quantity: "",
  old_operation_number: "",
  circuit_refs_new: "",
}

/** Minimal shape of the axios errors this component reacts to. Avoids `any`
 * (which the lint config rejects) without pulling in axios' own types. */
interface ApiError {
  response?: { status?: number; data?: { detail?: unknown } }
}

function toYyyymmdd(v: string): number | null {
  if (!v.trim()) return null
  return parseInt(v.replace(/-/g, ""), 10)
}

function splitRefs(raw: string): string[] | null {
  const refs = raw.split(",").map((r) => r.trim()).filter(Boolean)
  return refs.length > 0 ? refs : null
}

function formToBody(f: FormState): BOMChangeBody & { parent_item_number: string } {
  return {
    parent_item_number: f.parent_item_number.trim().toUpperCase(),
    change_type: f.change_type,
    component_number: f.component_number.trim().toUpperCase(),
    quantity: f.quantity.trim() ? parseFloat(f.quantity) : null,
    unit_of_measure: f.unit_of_measure.trim() || null,
    operation_number: f.operation_number.trim() ? parseInt(f.operation_number, 10) : null,
    sequence_number: f.sequence_number.trim() ? parseInt(f.sequence_number, 10) : null,
    from_date: toYyyymmdd(f.from_date),
    old_from_date: toYyyymmdd(f.old_from_date),
    old_quantity: f.old_quantity.trim() ? parseFloat(f.old_quantity) : null,
    old_operation_number: f.old_operation_number.trim()
      ? parseInt(f.old_operation_number, 10)
      : null,
    circuit_refs_new: splitRefs(f.circuit_refs_new),
  }
}

/** CHANGE/DELETE require old_from_date — it identifies the live Movex line
 * (MPDMAT key) being superseded. Mirrored client-side so Save disables before
 * a round trip surfaces the 422. */
function isFormValid(f: FormState): boolean {
  if (!f.parent_item_number.trim()) return false
  if (!f.component_number.trim()) return false
  if ((f.change_type === "CHANGE" || f.change_type === "DELETE") && !f.old_from_date.trim()) {
    return false
  }
  return true
}

interface Props {
  ecnId: string
  open: boolean
  onClose: () => void
  onSuccess?: () => void
}

export default function AddBomChangeDrawer({ ecnId, open, onClose, onSuccess }: Props) {
  const qc = useQueryClient()
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [apiError, setApiError] = useState<string | null>(null)

  // The parent whose live BOM is currently loaded — set by "Browse", not by
  // every keystroke, so typing doesn't fire an ERP call per character.
  const [browseItem, setBrowseItem] = useState<string | null>(null)
  const [browseInput, setBrowseInput] = useState("")

  const bomQuery = useQuery<BOMHead>({
    queryKey: ["bom", browseItem, "picker"],
    queryFn: () => fetchBOM(browseItem!),
    enabled: !!browseItem,
    retry: 1,
  })

  const createMut = useMutation({
    mutationFn: (body: BOMChangeBody & { parent_item_number: string }) =>
      createEcnScopedBomChange(ecnId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ecn-bom-changes-all", ecnId] })
      setForm({ ...EMPTY_FORM, parent_item_number: form.parent_item_number })
      setApiError(null)
      onSuccess?.()
    },
    onError: (err: ApiError) => {
      const detail = err?.response?.data?.detail
      setApiError(typeof detail === "string" ? detail : "Save failed — check the fields below.")
    },
  })

  if (!open) return null

  const set = (k: keyof FormState) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm((f) => ({ ...f, [k]: e.target.value }))

  function doBrowse(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = browseInput.trim().toUpperCase()
    if (!trimmed) return
    setBrowseItem(trimmed)
    // Browsing a parent is also declaring it — keep the form in step so the
    // user doesn't have to type the same number twice.
    setForm((f) => ({ ...f, parent_item_number: trimmed }))
  }

  /** Author a CHANGE/DELETE against a real live line. Old values come from
   * the line itself — old_from_date in particular must match the live MPDMAT
   * record, and hand-typing it is the most error-prone part of this form.
   *
   * Deliberately NOT named useLine: a `use*` name makes ESLint's
   * rules-of-hooks treat it as a React Hook and reject the onClick calls. */
  function applyLine(line: BOMLine, changeType: ChangeType) {
    setForm((f) => ({
      ...f,
      change_type: changeType,
      component_number: line.component_number,
      quantity: changeType === "DELETE" ? "" : String(line.quantity),
      unit_of_measure: line.unit_of_measure || "EA",
      operation_number: String(line.operation_number),
      sequence_number: String(line.sequence_number),
      old_quantity: String(line.quantity),
      old_operation_number: String(line.operation_number),
      old_from_date: String(line.from_date),
      circuit_refs_new: line.ref_des?.join(", ") ?? "",
    }))
    setApiError(null)
  }

  const notFound =
    bomQuery.isError && (bomQuery.error as ApiError)?.response?.status === 404
  const valid = isFormValid(form)
  const needsOld = form.change_type === "CHANGE" || form.change_type === "DELETE"

  return (
    <div className="fixed inset-0 z-[1050] flex justify-end bg-black/30" onClick={onClose}>
      <div
        className="w-full max-w-3xl h-full overflow-y-auto bg-white shadow-xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-white border-b border-neutral-200 px-6 py-4 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-neutral-900">Add BOM change</h2>
            <p className="text-xs text-neutral-500 mt-0.5">
              Name the parent assembly directly — no item needs to be on this ECN.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-neutral-400 hover:text-neutral-700 text-sm shrink-0"
          >
            Close
          </button>
        </div>

        <div className="px-6 py-5 space-y-5 flex-1">
          {/* ── BOM browser ─────────────────────────────────────────────── */}
          <section className="space-y-2">
            <p className="text-xs font-semibold text-neutral-500 uppercase tracking-wider">
              Browse the current BOM
            </p>
            <form onSubmit={doBrowse} className="flex items-center gap-2">
              <Input
                value={browseInput}
                onChange={(e) => setBrowseInput(e.target.value)}
                placeholder="Parent item number, e.g. LFAM050001"
                className="h-8 text-xs font-mono uppercase max-w-xs"
                aria-label="Parent item number to browse"
              />
              <Button type="submit" size="sm" className="h-8 text-xs" disabled={!browseInput.trim()}>
                Browse
              </Button>
              {bomQuery.isFetching && <Spinner size="sm" />}
            </form>

            {notFound && (
              <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
                No BOM found for <span className="font-mono">{browseItem}</span> in Movex. You can
                still author a change against it below if you are creating this structure.
              </p>
            )}
            {bomQuery.isError && !notFound && (
              <p className="text-xs text-red-600">
                Could not load the BOM — the ERP may be unavailable. You can still enter values
                manually below.
              </p>
            )}

            {bomQuery.data && (
              <div className="rounded-lg border border-neutral-200 overflow-hidden">
                <div className="bg-neutral-50 px-3 py-2 border-b border-neutral-200">
                  <span className="font-mono text-xs font-semibold text-[#0066cc]">
                    {bomQuery.data.item_number}
                  </span>
                  <span className="text-xs text-neutral-500 ml-2">{bomQuery.data.description}</span>
                  <span className="text-[10px] text-neutral-400 ml-2">
                    {bomQuery.data.lines.length} line(s) · facility {bomQuery.data.facility}
                  </span>
                </div>
                {/* Scroll region. The fade + "scroll for more" hint below
                    exist because a plain max-height cut a row in half at the
                    boundary, which reads as broken rather than scrollable. */}
                <div className="max-h-72 overflow-y-auto divide-y divide-neutral-100">
                  {bomQuery.data.lines.map((line) => (
                    <div
                      key={`${line.sequence_number}-${line.component_number}-${line.from_date}`}
                      className="group flex items-center gap-3 px-3 py-2 hover:bg-neutral-50"
                    >
                      <span className="font-mono text-[10px] text-neutral-400 w-8 shrink-0">
                        {line.sequence_number}
                      </span>
                      <div className="flex-1 min-w-0">
                        <span className="font-mono text-xs text-neutral-800">
                          {line.component_number}
                        </span>
                        <span className="text-[11px] text-neutral-500 ml-2 truncate">
                          {line.description}
                        </span>
                        <div className="text-[10px] text-neutral-400 mt-0.5">
                          {line.quantity} {line.unit_of_measure} · OPNO {line.operation_number} ·
                          from {fmtDate(line.from_date)}
                        </div>
                      </div>
                      {/* Always visible, not hover-revealed: these are the
                          primary actions of the picker. Hiding them until
                          hover made the lines look inert — a user could not
                          tell the rows were actionable at all. */}
                      <div className="flex gap-1 shrink-0">
                        <button
                          type="button"
                          onClick={() => applyLine(line, "CHANGE")}
                          className="text-[11px] font-medium text-blue-600 hover:bg-blue-50 rounded px-2 py-1 transition-colors"
                        >
                          Change
                        </button>
                        <button
                          type="button"
                          onClick={() => applyLine(line, "DELETE")}
                          className="text-[11px] font-medium text-red-600 hover:bg-red-50 rounded px-2 py-1 transition-colors"
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  ))}
                  {bomQuery.data.lines.length === 0 && (
                    <p className="text-xs text-neutral-400 px-3 py-4 text-center">
                      This structure has no components yet.
                    </p>
                  )}
                </div>
                {bomQuery.data.lines.length > 4 && (
                  <div className="bg-neutral-50 border-t border-neutral-200 px-3 py-1 text-center">
                    <span className="text-[10px] text-neutral-400">
                      Scroll for all {bomQuery.data.lines.length} lines
                    </span>
                  </div>
                )}
              </div>
            )}
          </section>

          {/* ── The change itself ───────────────────────────────────────── */}
          <section className="space-y-3 border-t border-neutral-100 pt-5">
            <p className="text-xs font-semibold text-neutral-500 uppercase tracking-wider">
              The change
            </p>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs font-medium text-neutral-600">
                  Parent item <span className="text-red-500">*</span>
                </Label>
                <Input
                  value={form.parent_item_number}
                  onChange={set("parent_item_number")}
                  className="h-8 text-xs font-mono uppercase"
                  placeholder="LFAM050001"
                />
                <p className="text-[10px] text-neutral-400">
                  Must already exist in Movex — verified on save.
                </p>
              </div>
              <div className="space-y-1">
                <Label className="text-xs font-medium text-neutral-600">
                  Change type <span className="text-red-500">*</span>
                </Label>
                <select
                  value={form.change_type}
                  onChange={set("change_type")}
                  className="h-8 w-full rounded-md border border-neutral-200 bg-white px-2 text-xs focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:ring-offset-1"
                >
                  {CHANGE_TYPES.map((ct) => (
                    <option key={ct} value={ct}>{CHANGE_TYPE_LABEL[ct]}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="space-y-1">
              <Label className="text-xs font-medium text-neutral-600">
                Component <span className="text-red-500">*</span>
              </Label>
              <Input
                value={form.component_number}
                onChange={set("component_number")}
                className="h-8 text-xs font-mono uppercase"
                placeholder="LF200010"
              />
            </div>

            {form.change_type !== "DELETE" && (
              <div className="grid grid-cols-4 gap-3">
                <div className="space-y-1">
                  <Label className="text-xs font-medium text-neutral-600">Quantity</Label>
                  <Input type="number" step={0.000001} value={form.quantity}
                         onChange={set("quantity")} className="h-8 text-xs font-mono" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs font-medium text-neutral-600">UOM</Label>
                  <Input value={form.unit_of_measure} onChange={set("unit_of_measure")}
                         maxLength={3} className="h-8 text-xs font-mono" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs font-medium text-neutral-600">Operation</Label>
                  <Input type="number" value={form.operation_number}
                         onChange={set("operation_number")} className="h-8 text-xs font-mono" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs font-medium text-neutral-600">Sequence</Label>
                  <Input type="number" value={form.sequence_number}
                         onChange={set("sequence_number")} className="h-8 text-xs font-mono" />
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs font-medium text-neutral-600">
                  From date (YYYYMMDD)
                </Label>
                <Input value={form.from_date} onChange={set("from_date")}
                       className="h-8 text-xs font-mono" placeholder="20260901" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs font-medium text-neutral-600">
                  Old from date (YYYYMMDD)
                  {needsOld && <span className="text-red-500"> *</span>}
                </Label>
                <Input value={form.old_from_date} onChange={set("old_from_date")}
                       className="h-8 text-xs font-mono" placeholder="20240101" />
                {needsOld && !form.old_from_date.trim() && (
                  <p className="text-[10px] text-red-500">
                    Required for {form.change_type} — identifies the live Movex line. Pick the line
                    above to fill this correctly.
                  </p>
                )}
              </div>
            </div>

            {form.change_type !== "DELETE" && (
              <div className="space-y-1">
                <Label className="text-xs font-medium text-neutral-600">
                  Reference designators (comma-separated)
                </Label>
                <Input value={form.circuit_refs_new} onChange={set("circuit_refs_new")}
                       className="h-8 text-xs font-mono" placeholder="R1, R7, R12" />
              </div>
            )}

            {apiError && (
              <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
                {apiError}
              </p>
            )}
          </section>
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 bg-white border-t border-neutral-200 px-6 py-3 flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" className="h-8 text-xs"
                  onClick={onClose} disabled={createMut.isPending}>
            Done
          </Button>
          <Button type="button" size="sm" className="h-8 text-xs min-w-[110px]"
                  onClick={() => createMut.mutate(formToBody(form))}
                  disabled={!valid || createMut.isPending}>
            {createMut.isPending ? <Spinner size="sm" /> : "Add BOM change"}
          </Button>
        </div>
      </div>
    </div>
  )
}
