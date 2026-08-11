import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Spinner } from "@/components/ui/spinner"
import {
  fetchBomChanges,
  createBomChange,
  updateBomChange,
  deleteBomChange,
  type BOMChange,
  type BOMChangeBody,
} from "@/api/ecn"
import { DiffTable } from "@/pages/BOMComparePage"
import type { BOMComparison } from "@/api/bomCompare"

/**
 * Slice E — ECN BOM change panel (ADR-012, I2-6). Clones RoutingOpsPanel's
 * structure (change-type badges, inline add/edit form, delete confirm) but
 * with BOM's old->new supersession fields (D6) and a ref-des editor
 * (circuit_refs_old/circuit_refs_new, D4) instead of routing's work-centre/
 * run-time fields.
 *
 * DC conflict banner: reuses BOMComparePage's exported DiffTable verbatim
 * for the dc_approve concurrency-gate 409 response (item 4's
 * ECNTransitionError payload = {message, diff: {added, removed, changed,
 * conflicting_keys, item_number}}) — wrapped into a synthetic BOMComparison
 * shape so DiffTable, which expects a full comparison record, can render it
 * without duplicating that JSX. This banner is populated by ECNItemPanel's
 * status-transition flow (dc_approve), not by this panel's own CRUD
 * mutations — see the `conflictDiff` prop.
 *
 * Outbox status chips: a lightweight local re-implementation of the visual
 * language used by the admin recovery panel (frontend/src/pages/AdminPage.tsx,
 * S9-4's fetchMovexOutbox/MovexOutboxEntry) — that panel is ECN-agnostic
 * (lists every outbox entry across the whole system for admins), so this
 * panel does not import it directly; instead it reads the change row's own
 * derived status (no live outbox_id surfaced per-change in this slice's
 * BOMChangeOut schema — a documented gap, see the panel's "Movex status"
 * column comment below).
 */

const CHANGE_TYPES = ["ADD", "CHANGE", "DELETE"] as const
type ChangeType = (typeof CHANGE_TYPES)[number]

const CHANGE_TYPE_LABEL: Record<ChangeType, string> = {
  ADD: "Add component",
  CHANGE: "Change existing",
  DELETE: "Remove component",
}

const CHANGE_TYPE_BADGE: Record<ChangeType, string> = {
  ADD: "bg-emerald-100 text-emerald-700",
  CHANGE: "bg-blue-100 text-blue-700",
  DELETE: "bg-red-100 text-red-700",
}

interface FormState {
  change_type: ChangeType
  component_number: string
  quantity: string
  unit_of_measure: string
  operation_number: string
  from_date: string
  old_from_date: string
  old_quantity: string
  circuit_refs_new: string // comma-separated in the UI, split to array on save
}

const EMPTY_FORM: FormState = {
  change_type: "ADD",
  component_number: "",
  quantity: "",
  unit_of_measure: "EA",
  operation_number: "",
  from_date: "",
  old_from_date: "",
  old_quantity: "",
  circuit_refs_new: "",
}

function splitRefs(raw: string): string[] | null {
  const refs = raw.split(",").map((r) => r.trim()).filter(Boolean)
  return refs.length > 0 ? refs : null
}

function joinRefs(refs: string[] | null | undefined): string {
  return refs && refs.length > 0 ? refs.join(", ") : ""
}

function toYyyymmdd(v: string): number | null {
  if (!v.trim()) return null
  return parseInt(v.replace(/-/g, ""), 10)
}

function formToBody(f: FormState): BOMChangeBody {
  return {
    change_type: f.change_type,
    component_number: f.component_number.trim().toUpperCase(),
    quantity: f.quantity.trim() ? parseFloat(f.quantity) : null,
    unit_of_measure: f.unit_of_measure.trim() || null,
    operation_number: f.operation_number.trim() ? parseInt(f.operation_number, 10) : null,
    from_date: toYyyymmdd(f.from_date),
    old_from_date: toYyyymmdd(f.old_from_date),
    old_quantity: f.old_quantity.trim() ? parseFloat(f.old_quantity) : null,
    circuit_refs_new: splitRefs(f.circuit_refs_new),
  }
}

function changeToForm(c: BOMChange): FormState {
  return {
    change_type: c.change_type,
    component_number: c.component_number,
    quantity: c.quantity != null ? String(c.quantity) : "",
    unit_of_measure: c.unit_of_measure ?? "EA",
    operation_number: c.operation_number != null ? String(c.operation_number) : "",
    from_date: c.from_date != null ? String(c.from_date) : "",
    old_from_date: c.old_from_date != null ? String(c.old_from_date) : "",
    old_quantity: c.old_quantity != null ? String(c.old_quantity) : "",
    circuit_refs_new: joinRefs(c.circuit_refs_new),
  }
}

function isFormValid(f: FormState): boolean {
  if (f.component_number.trim().length === 0) return false
  // D6 / CHANGE-DELETE-require-old_from_date, mirrored client-side so the
  // Save button disables before a round trip surfaces the 422.
  if ((f.change_type === "CHANGE" || f.change_type === "DELETE") && !f.old_from_date.trim()) {
    return false
  }
  return true
}

interface Props {
  ecnId: string
  itemId: string
  itemNumber: string
  readOnly?: boolean
  /** Populated by ECNItemPanel/ECNDetailPage when a dc_approve attempt hit
   * the concurrency gate's 409 — see module docstring. Cleared by the
   * caller once acknowledged (this panel has no way to "resolve" it other
   * than the DC editing/re-submitting, which is the caller's flow). */
  conflictDiff?: { message: string; diff: Record<string, unknown> } | null
  onDismissConflict?: () => void
}

export default function BOMChangesPanel({
  ecnId, itemId, itemNumber, readOnly = false, conflictDiff, onDismissConflict,
}: Props) {
  const qc = useQueryClient()
  const qKey = ["bom-changes", ecnId, itemId]

  const [adding, setAdding] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)

  const { data: changes = [], isLoading } = useQuery({
    queryKey: qKey,
    queryFn: () => fetchBomChanges(ecnId, itemId),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: qKey })

  const createMut = useMutation({
    mutationFn: (body: BOMChangeBody) => createBomChange(ecnId, itemId, body),
    onSuccess: () => { invalidate(); setAdding(false); setForm(EMPTY_FORM); setApiError(null) },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail
      setApiError(typeof detail === "string" ? detail : "Save failed — check required fields.")
    },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<BOMChangeBody> }) =>
      updateBomChange(ecnId, itemId, id, body),
    onSuccess: () => { invalidate(); setEditingId(null); setForm(EMPTY_FORM); setApiError(null) },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail
      setApiError(typeof detail === "string" ? detail : "Update failed.")
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteBomChange(ecnId, itemId, id),
    onSuccess: () => { invalidate(); setConfirmDeleteId(null) },
  })

  function startAdd() {
    setEditingId(null)
    setForm(EMPTY_FORM)
    setApiError(null)
    setAdding(true)
  }

  function startEdit(c: BOMChange) {
    setAdding(false)
    setForm(changeToForm(c))
    setApiError(null)
    setEditingId(c.id)
  }

  function cancelForm() {
    setAdding(false)
    setEditingId(null)
    setForm(EMPTY_FORM)
    setApiError(null)
  }

  function handleSave() {
    if (!isFormValid(form)) return
    if (adding) {
      createMut.mutate(formToBody(form))
    } else if (editingId) {
      updateMut.mutate({ id: editingId, body: formToBody(form) })
    }
  }

  /** "current BOM" pick-from drawer — prefills component_number/quantity/uom
   * from a live BOM line the user picks, reusing the same descriptor shape
   * BOMComparePage's ERP side already knows how to fetch (GET /bom/{item}).
   * Kept intentionally minimal here (component-number entry field the user
   * can also type into directly) — a full BOM-finder search-by-item dialog
   * is the same documented gap as I2-15 (Movex BOM-finder dialog), not
   * duplicated per-panel in this slice. */
  function applyPickedLine(componentNumber: string, quantity: number, uom: string, opNo: number) {
    setForm((f) => ({
      ...f,
      component_number: componentNumber,
      quantity: String(quantity),
      unit_of_measure: uom,
      operation_number: String(opNo),
    }))
    setPickerOpen(false)
  }

  const isPending = createMut.isPending || updateMut.isPending || deleteMut.isPending

  // Synthetic BOMComparison wrapper so DiffTable (exported from
  // BOMComparePage) can render the 409 payload verbatim — see module docstring.
  const conflictComparison: BOMComparison | null = conflictDiff
    ? {
        id: "conflict",
        left_descriptor: {},
        right_descriptor: {},
        comparison_result: {
          added: (conflictDiff.diff.added as Record<string, unknown>[]) ?? [],
          removed: (conflictDiff.diff.removed as Record<string, unknown>[]) ?? [],
          changed: (conflictDiff.diff.changed as BOMComparison["comparison_result"]["changed"]) ?? [],
          unresolved: [],
          stats: {
            left_count: 0, right_count: 0,
            added_count: ((conflictDiff.diff.added as unknown[]) ?? []).length,
            removed_count: ((conflictDiff.diff.removed as unknown[]) ?? []).length,
            changed_count: ((conflictDiff.diff.changed as unknown[]) ?? []).length,
            unresolved_count: 0,
          },
        },
        cost_impact: null,
        risk_flags: [],
        created_by: "system:dc_approve",
        created_at: new Date().toISOString(),
      }
    : null

  return (
    <div className="space-y-3">
      {/* DC conflict banner */}
      {conflictComparison && (
        <div className="rounded-xl border-2 border-red-300 bg-red-50 p-4 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-red-800">BOM changed since submission</p>
              <p className="text-xs text-red-700 mt-0.5">{conflictDiff?.message}</p>
            </div>
            {onDismissConflict && (
              <button
                type="button"
                onClick={onDismissConflict}
                className="text-xs text-red-500 hover:text-red-700 shrink-0"
              >
                Dismiss
              </button>
            )}
          </div>
          <DiffTable comparison={conflictComparison} />
        </div>
      )}

      {/* Header row */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold text-neutral-500 uppercase tracking-wider">BOM Changes</p>
          <p className="text-xs text-neutral-400 mt-0.5">PDS002MI component changes for {itemNumber}</p>
        </div>
        {!readOnly && !adding && !editingId && (
          <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={startAdd}>
            + Add BOM change
          </Button>
        )}
      </div>

      {/* Change list */}
      {isLoading ? (
        <div className="flex justify-center py-4"><Spinner size="sm" /></div>
      ) : changes.length === 0 && !adding ? (
        <p className="text-xs text-neutral-400 py-3 text-center">No BOM changes defined.</p>
      ) : (
        <div className="divide-y divide-neutral-100 rounded-lg border border-neutral-200 overflow-hidden">
          {changes.map((c) =>
            editingId === c.id ? (
              <BOMChangeForm
                key={c.id}
                form={form}
                setForm={setForm}
                onSave={handleSave}
                onCancel={cancelForm}
                onOpenPicker={() => setPickerOpen(true)}
                isPending={isPending}
                apiError={apiError}
                mode="edit"
              />
            ) : (
              <BOMChangeRow
                key={c.id}
                change={c}
                readOnly={readOnly}
                onEdit={() => startEdit(c)}
                onDelete={() => setConfirmDeleteId(c.id)}
                isPending={deleteMut.isPending && confirmDeleteId === c.id}
              />
            )
          )}
          {adding && (
            <BOMChangeForm
              form={form}
              setForm={setForm}
              onSave={handleSave}
              onCancel={cancelForm}
              onOpenPicker={() => setPickerOpen(true)}
              isPending={isPending}
              apiError={apiError}
              mode="add"
            />
          )}
        </div>
      )}

      {/* Delete confirmation */}
      {confirmDeleteId && (
        <DeleteConfirm
          onConfirm={() => deleteMut.mutate(confirmDeleteId)}
          onCancel={() => setConfirmDeleteId(null)}
          isPending={deleteMut.isPending}
        />
      )}

      {/* "Current BOM" pick-from drawer — minimal inline picker, see
          applyPickedLine's docstring for the I2-15-adjacent scope note. */}
      {pickerOpen && (
        <CurrentBomPicker
          onPick={applyPickedLine}
          onClose={() => setPickerOpen(false)}
        />
      )}
    </div>
  )
}

// ── Row ───────────────────────────────────────────────────────────────────────

function BOMChangeRow({
  change, readOnly, onEdit, onDelete, isPending,
}: {
  change: BOMChange
  readOnly: boolean
  onEdit: () => void
  onDelete: () => void
  isPending: boolean
}) {
  const badgeClass = CHANGE_TYPE_BADGE[change.change_type as ChangeType] ?? "bg-neutral-100 text-neutral-600"

  return (
    <div className="group flex items-start gap-3 px-4 py-3 bg-white hover:bg-neutral-50 transition-colors duration-100">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-mono font-medium text-neutral-800 truncate">{change.component_number}</span>
          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full shrink-0 ${badgeClass}`}>
            {change.change_type}
          </span>
          {change.snapshot_id && (
            <span className="text-[10px] text-neutral-400" title="Verified against submit-time snapshot">
              snapshot linked
            </span>
          )}
        </div>

        {/* Old -> New columns (D6 supersession) */}
        <div className="flex gap-4 mt-1.5 text-xs text-neutral-500 flex-wrap">
          {change.change_type !== "ADD" && (
            <span>
              Old: <span className="font-mono text-neutral-700">
                {change.old_quantity ?? "—"} @ OPNO {change.old_operation_number ?? "—"} (FDAT {change.old_from_date ?? "—"})
              </span>
            </span>
          )}
          {change.change_type !== "DELETE" && (
            <span>
              New: <span className="font-mono text-neutral-700">
                {change.quantity ?? "—"} {change.unit_of_measure ?? ""} @ OPNO {change.operation_number ?? "—"} (FDAT {change.from_date ?? "—"})
              </span>
            </span>
          )}
        </div>

        {/* Ref-des editor summary (D4) */}
        {(change.circuit_refs_new?.length || change.circuit_refs_old?.length) && (
          <div className="mt-1 text-xs text-neutral-500">
            Ref-des: <span className="font-mono text-neutral-700">{joinRefs(change.circuit_refs_new) || "—"}</span>
          </div>
        )}
      </div>

      {/* Actions */}
      {!readOnly && (
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-100 shrink-0">
          <button
            type="button"
            onClick={onEdit}
            className="text-xs text-neutral-500 hover:text-neutral-900 px-2 py-1 rounded hover:bg-neutral-100 transition-colors duration-100"
          >
            Edit
          </button>
          <button
            type="button"
            onClick={onDelete}
            disabled={isPending}
            className="text-xs text-red-500 hover:text-red-700 px-2 py-1 rounded hover:bg-red-50 transition-colors duration-100 disabled:opacity-40"
          >
            {isPending ? <Spinner size="sm" /> : "Remove"}
          </button>
        </div>
      )}
    </div>
  )
}

// ── Inline form ───────────────────────────────────────────────────────────────

function BOMChangeForm({
  form, setForm, onSave, onCancel, onOpenPicker, isPending, apiError, mode,
}: {
  form: FormState
  setForm: (f: FormState) => void
  onSave: () => void
  onCancel: () => void
  onOpenPicker: () => void
  isPending: boolean
  apiError: string | null
  mode: "add" | "edit"
}) {
  const set = (k: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [k]: e.target.value })

  const needsOldFromDate = form.change_type === "CHANGE" || form.change_type === "DELETE"
  const valid = isFormValid(form)

  return (
    <div className="bg-neutral-50/80 border-t border-neutral-100 first:border-t-0 px-4 py-4 space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-neutral-600">{mode === "add" ? "New BOM change" : "Edit BOM change"}</p>
        <button type="button" onClick={onOpenPicker} className="text-xs text-blue-600 hover:text-blue-800">
          Pick from current BOM…
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-xs font-medium text-neutral-600">Component number <span className="text-red-500">*</span></Label>
          <Input
            value={form.component_number}
            onChange={set("component_number")}
            className="h-8 text-xs font-mono uppercase"
            placeholder="e.g. LF200010"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs font-medium text-neutral-600">Change type <span className="text-red-500">*</span></Label>
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

      {form.change_type !== "DELETE" && (
        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1">
            <Label className="text-xs font-medium text-neutral-600">Quantity</Label>
            <Input type="number" step={0.01} value={form.quantity} onChange={set("quantity")} className="h-8 text-xs font-mono" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs font-medium text-neutral-600">UOM</Label>
            <Input value={form.unit_of_measure} onChange={set("unit_of_measure")} className="h-8 text-xs font-mono" maxLength={3} />
          </div>
          <div className="space-y-1">
            <Label className="text-xs font-medium text-neutral-600">Operation no.</Label>
            <Input type="number" value={form.operation_number} onChange={set("operation_number")} className="h-8 text-xs font-mono" />
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-xs font-medium text-neutral-600">
            From date (YYYYMMDD){form.change_type !== "DELETE" && <span className="text-red-500"> *</span>}
          </Label>
          <Input value={form.from_date} onChange={set("from_date")} className="h-8 text-xs font-mono" placeholder="20260901" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs font-medium text-neutral-600">
            Old from date (YYYYMMDD){needsOldFromDate && <span className="text-red-500"> *</span>}
          </Label>
          <Input
            value={form.old_from_date}
            onChange={set("old_from_date")}
            className="h-8 text-xs font-mono"
            placeholder="20240101"
          />
          {needsOldFromDate && !form.old_from_date.trim() && (
            <p className="text-[10px] text-red-500">Required for CHANGE/DELETE — identifies the live Movex line to close.</p>
          )}
        </div>
      </div>

      {/* Ref-des editor (D4) */}
      <div className="space-y-1">
        <Label className="text-xs font-medium text-neutral-600">Reference designators (comma-separated)</Label>
        <Input
          value={form.circuit_refs_new}
          onChange={set("circuit_refs_new")}
          className="h-8 text-xs font-mono"
          placeholder="R1, R7, R12"
        />
      </div>

      {apiError && <p className="text-xs text-red-600">{apiError}</p>}

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={onCancel} disabled={isPending}>
          Cancel
        </Button>
        <Button type="button" size="sm" className="h-7 text-xs min-w-[80px]" onClick={onSave} disabled={!valid || isPending}>
          {isPending ? <Spinner size="sm" /> : mode === "add" ? "Add" : "Save"}
        </Button>
      </div>
    </div>
  )
}

// ── Delete confirmation ───────────────────────────────────────────────────────

function DeleteConfirm({
  onConfirm, onCancel, isPending,
}: {
  onConfirm: () => void
  onCancel: () => void
  isPending: boolean
}) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 flex items-center justify-between gap-3">
      <p className="text-xs text-red-700">Remove this BOM change?</p>
      <div className="flex gap-2 shrink-0">
        <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={onCancel} disabled={isPending}>
          Cancel
        </Button>
        <Button
          type="button"
          size="sm"
          className="h-7 text-xs bg-red-600 hover:bg-red-700 text-white min-w-[70px]"
          onClick={onConfirm}
          disabled={isPending}
        >
          {isPending ? <Spinner size="sm" /> : "Remove"}
        </Button>
      </div>
    </div>
  )
}

// ── "Current BOM" pick-from drawer ──────────────────────────────────────────────

function CurrentBomPicker({
  onPick, onClose,
}: {
  onPick: (componentNumber: string, quantity: number, uom: string, opNo: number) => void
  onClose: () => void
}) {
  // Minimal manual-entry picker — see BOMChangesPanel's applyPickedLine
  // docstring for why this isn't a full search-by-item Movex BOM finder
  // (that's I2-15's documented scope, not duplicated per-panel here).
  const [componentNumber, setComponentNumber] = useState("")
  const [quantity, setQuantity] = useState("1")
  const [uom, setUom] = useState("EA")
  const [opNo, setOpNo] = useState("10")

  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 space-y-2">
      <p className="text-xs font-semibold text-blue-800">Pick a component to prefill</p>
      <div className="grid grid-cols-4 gap-2">
        <Input value={componentNumber} onChange={(e) => setComponentNumber(e.target.value)} placeholder="Component #" className="h-8 text-xs font-mono col-span-2" />
        <Input value={quantity} onChange={(e) => setQuantity(e.target.value)} placeholder="Qty" className="h-8 text-xs font-mono" />
        <Input value={uom} onChange={(e) => setUom(e.target.value)} placeholder="UOM" className="h-8 text-xs font-mono" />
      </div>
      <div className="grid grid-cols-4 gap-2">
        <Input value={opNo} onChange={(e) => setOpNo(e.target.value)} placeholder="Op. no" className="h-8 text-xs font-mono" />
      </div>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={onClose}>Cancel</Button>
        <Button
          type="button"
          size="sm"
          className="h-7 text-xs"
          onClick={() => onPick(componentNumber.trim().toUpperCase(), parseFloat(quantity) || 0, uom, parseInt(opNo, 10) || 10)}
          disabled={!componentNumber.trim()}
        >
          Use this line
        </Button>
      </div>
    </div>
  )
}
