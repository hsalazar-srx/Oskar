import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Spinner } from "@/components/ui/spinner"
import { createRoutingOp, type RoutingOpBody } from "@/api/ecn"

/**
 * ADR-016 — add a routing operation from the ECN-wide Routing tab, with no
 * item on the ECN required.
 *
 * Before this, a routing change could only be authored through an ecn_items
 * row (ecn_routing_operations.ecn_item_id was NOT NULL), so an ECN that only
 * revises a routing had to carry a dummy item row telling reviewers the item
 * master was changing when it was not. Stargile never worked this way:
 * ZECNROUT carries its own RTPRNO alongside the operation fields, with no
 * pointer to an items table.
 *
 * Mirrors AddMpnDrawer. No ERP browse yet — reading current M3 operations
 * needs PDS002MI.LstOperation exposed as a route; the adapter method exists
 * (get_routing_operations) but nothing calls it. That is the prerequisite for
 * the routing side of the before/after comparison too.
 */

const CHANGE_TYPES = ["ADD", "UPDATE", "DELETE"] as const
type ChangeType = (typeof CHANGE_TYPES)[number]

const CHANGE_TYPE_LABEL: Record<ChangeType, string> = {
  ADD: "Add operation",
  UPDATE: "Change existing",
  DELETE: "Remove operation",
}

interface FormState {
  item_number: string
  operation_number: string
  operation_description: string
  work_centre: string
  run_time: string
  setup_time: string
  change_type: ChangeType
}

const EMPTY_FORM: FormState = {
  item_number: "",
  operation_number: "",
  operation_description: "",
  work_centre: "",
  run_time: "",
  setup_time: "",
  change_type: "ADD",
}

/** Minimal shape of the axios errors this component reacts to. Avoids `any`,
 * which the lint config rejects. */
interface ApiError {
  response?: { status?: number; data?: { detail?: unknown } }
}

function formToBody(f: FormState): RoutingOpBody & { item_number: string } {
  return {
    item_number: f.item_number.trim().toUpperCase(),
    operation_number: parseInt(f.operation_number, 10),
    operation_description: f.operation_description.trim(),
    work_centre: f.work_centre.trim().toUpperCase(),
    run_time: parseFloat(f.run_time),
    setup_time: f.setup_time.trim() ? parseFloat(f.setup_time) : null,
    change_type: f.change_type,
  }
}

function isFormValid(f: FormState): boolean {
  if (!f.item_number.trim()) return false
  if (!f.operation_number.trim() || parseInt(f.operation_number, 10) < 1) return false
  if (!f.operation_description.trim()) return false
  if (!f.work_centre.trim()) return false
  // run_time is required and must parse — 0 is legitimate, so check the parse
  // rather than truthiness.
  return Number.isFinite(parseFloat(f.run_time))
}

/** Next operation number: highest already entered for this item, rounded up
 * to the next multiple of 10. Matches RoutingOpsPanel's (ops.length + 1) * 10
 * convention and the MSEQ suggestion in AddBomChangeDrawer — M3 routings are
 * sparse so consecutive numbering would collide on insert. */
function suggestNextOpNo(existing: number[]): number {
  if (existing.length === 0) return 10
  return Math.floor(Math.max(...existing) / 10) * 10 + 10
}

interface Props {
  ecnId: string
  open: boolean
  onClose: () => void
  onSuccess?: () => void
  /** Operation numbers already on this ECN for the item currently typed —
   * used only to suggest the next free number. */
  existingOpNumbersFor?: (itemNumber: string) => number[]
}

export default function AddRoutingOpDrawer({
  ecnId,
  open,
  onClose,
  onSuccess,
  existingOpNumbersFor,
}: Props) {
  const qc = useQueryClient()
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [apiError, setApiError] = useState<string | null>(null)
  const [lastAdded, setLastAdded] = useState<string | null>(null)

  const createMut = useMutation({
    mutationFn: (body: RoutingOpBody & { item_number: string }) =>
      createRoutingOp(ecnId, null, body),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["ecn-routing-all", ecnId] })
      setLastAdded(`${created.operation_number} on ${created.item_number ?? ""}`.trim())
      // Keep the item number: adding several operations to one routing is the
      // common case, and retyping it every time is the friction this drawer
      // exists to remove.
      setForm({ ...EMPTY_FORM, item_number: form.item_number })
      setApiError(null)
      onSuccess?.()
    },
    onError: (err: ApiError) => {
      const detail = err?.response?.data?.detail
      if (err?.response?.status === 409) {
        setApiError(
          "An operation with this number already exists on this item for this ECN.",
        )
        return
      }
      setApiError(
        typeof detail === "string" ? detail : "Save failed — check the fields below.",
      )
    },
  })

  if (!open) return null

  const set =
    (k: keyof FormState) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm((f) => ({ ...f, [k]: e.target.value }))

  const valid = isFormValid(form)
  const suggestion =
    existingOpNumbersFor && form.item_number.trim()
      ? suggestNextOpNo(existingOpNumbersFor(form.item_number.trim().toUpperCase()))
      : null

  return (
    <div className="fixed inset-0 z-[1050] flex justify-end bg-black/30" onClick={onClose}>
      <div
        className="w-full max-w-2xl h-full overflow-y-auto bg-white shadow-xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-white border-b border-neutral-200 px-6 py-4 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-neutral-900">Add routing operation</h2>
            <p className="text-xs text-neutral-500 mt-0.5">
              Name the product directly — it does not need to be on this ECN.
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

        <div className="px-6 py-5 space-y-4 flex-1">
          {lastAdded && !apiError && (
            <p className="text-xs text-green-700 bg-green-50 border border-green-200 rounded px-3 py-2">
              Added operation <span className="font-mono">{lastAdded}</span>. Add another
              below, or close.
            </p>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs font-medium text-neutral-600">
                Item number <span className="text-red-500">*</span>
              </Label>
              <Input
                value={form.item_number}
                onChange={set("item_number")}
                className="h-8 text-xs font-mono uppercase"
                placeholder="LF100001"
              />
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

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs font-medium text-neutral-600">
                Operation number <span className="text-red-500">*</span>
              </Label>
              <Input
                type="number"
                min={1}
                value={form.operation_number}
                onChange={set("operation_number")}
                className="h-8 text-xs font-mono"
                placeholder="10"
              />
              {suggestion !== null && !form.operation_number.trim() && (
                <button
                  type="button"
                  onClick={() =>
                    setForm((f) => ({ ...f, operation_number: String(suggestion) }))
                  }
                  className="text-[10px] text-blue-600 hover:text-blue-800"
                >
                  Use {suggestion}
                </button>
              )}
            </div>
            <div className="space-y-1">
              <Label className="text-xs font-medium text-neutral-600">
                Work centre <span className="text-red-500">*</span>
              </Label>
              <Input
                value={form.work_centre}
                onChange={set("work_centre")}
                maxLength={8}
                className="h-8 text-xs font-mono uppercase"
                placeholder="SMT01"
              />
            </div>
          </div>

          <div className="space-y-1">
            <Label className="text-xs font-medium text-neutral-600">
              Operation description <span className="text-red-500">*</span>
            </Label>
            <Input
              value={form.operation_description}
              onChange={set("operation_description")}
              maxLength={30}
              className="h-8 text-xs"
              placeholder="SMT placement"
            />
            <p className="text-[10px] text-neutral-400">
              Max 30 characters — M3 truncates beyond that (POOPDS).
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs font-medium text-neutral-600">
                Run time (min) <span className="text-red-500">*</span>
              </Label>
              <Input
                type="number"
                min={0}
                step={0.01}
                value={form.run_time}
                onChange={set("run_time")}
                className="h-8 text-xs font-mono"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs font-medium text-neutral-600">Setup time (min)</Label>
              <Input
                type="number"
                min={0}
                step={0.01}
                value={form.setup_time}
                onChange={set("setup_time")}
                className="h-8 text-xs font-mono"
              />
              <p className="text-[10px] text-neutral-400">
                Stored in Oskar only — M3's AddOperation has no setup-time field.
              </p>
            </div>
          </div>

          {apiError && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
              {apiError}
            </p>
          )}
        </div>

        <div className="sticky bottom-0 bg-white border-t border-neutral-200 px-6 py-3 flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 text-xs"
            onClick={onClose}
            disabled={createMut.isPending}
          >
            Done
          </Button>
          <Button
            type="button"
            size="sm"
            className="h-8 text-xs min-w-[110px]"
            onClick={() => createMut.mutate(formToBody(form))}
            disabled={!valid || createMut.isPending}
          >
            {createMut.isPending ? <Spinner size="sm" /> : "Add operation"}
          </Button>
        </div>
      </div>
    </div>
  )
}
