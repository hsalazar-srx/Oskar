import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Spinner } from "@/components/ui/spinner"
import {
  fetchRoutingOps,
  createRoutingOp,
  updateRoutingOp,
  deleteRoutingOp,
  type RoutingOp,
  type RoutingOpBody,
} from "@/api/ecn"

const CHANGE_TYPES = ["ADD", "UPDATE", "DELETE"] as const
type ChangeType = (typeof CHANGE_TYPES)[number]

const CHANGE_TYPE_LABEL: Record<ChangeType, string> = {
  ADD: "Add operation",
  UPDATE: "Update existing",
  DELETE: "Remove operation",
}

const CHANGE_TYPE_BADGE: Record<ChangeType, string> = {
  ADD: "bg-emerald-100 text-emerald-700",
  UPDATE: "bg-blue-100 text-blue-700",
  DELETE: "bg-red-100 text-red-700",
}

interface FormState {
  operation_number: string
  operation_description: string
  work_centre: string
  run_time: string
  setup_time: string
  change_type: ChangeType
}

const EMPTY_FORM: FormState = {
  operation_number: "",
  operation_description: "",
  work_centre: "",
  run_time: "",
  setup_time: "",
  change_type: "ADD",
}

function formToBody(f: FormState): RoutingOpBody {
  return {
    operation_number: parseInt(f.operation_number, 10),
    operation_description: f.operation_description.trim(),
    work_centre: f.work_centre.trim().toUpperCase(),
    run_time: parseFloat(f.run_time),
    setup_time: f.setup_time.trim() ? parseFloat(f.setup_time) : null,
    change_type: f.change_type,
  }
}

function opToForm(op: RoutingOp): FormState {
  return {
    operation_number: String(op.operation_number),
    operation_description: op.operation_description,
    work_centre: op.work_centre,
    run_time: String(op.run_time),
    setup_time: op.setup_time != null ? String(op.setup_time) : "",
    change_type: op.change_type as ChangeType,
  }
}

function isFormValid(f: FormState): boolean {
  return (
    f.operation_number.trim() !== "" &&
    !isNaN(parseInt(f.operation_number, 10)) &&
    parseInt(f.operation_number, 10) >= 1 &&
    f.operation_description.trim().length >= 1 &&
    f.operation_description.trim().length <= 30 &&
    f.work_centre.trim().length >= 1 &&
    f.work_centre.trim().length <= 8 &&
    f.run_time.trim() !== "" &&
    !isNaN(parseFloat(f.run_time)) &&
    parseFloat(f.run_time) >= 0 &&
    (f.setup_time.trim() === "" || (!isNaN(parseFloat(f.setup_time)) && parseFloat(f.setup_time) >= 0))
  )
}

interface Props {
  ecnId: string
  itemId: string
  itemNumber: string
  readOnly?: boolean
}

export default function RoutingOpsPanel({ ecnId, itemId, itemNumber, readOnly = false }: Props) {
  const qc = useQueryClient()
  const qKey = ["routing-ops", ecnId, itemId]

  const [adding, setAdding] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)

  const { data: ops = [], isLoading } = useQuery({
    queryKey: qKey,
    queryFn: () => fetchRoutingOps(ecnId, itemId),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: qKey })

  const createMut = useMutation({
    mutationFn: (body: RoutingOpBody) => createRoutingOp(ecnId, itemId, body),
    onSuccess: () => { invalidate(); setAdding(false); setForm(EMPTY_FORM); setApiError(null) },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail
      setApiError(typeof detail === "string" ? detail : "Save failed — check for duplicate operation number.")
    },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<Omit<RoutingOpBody, "operation_number">> }) =>
      updateRoutingOp(ecnId, itemId, id, body),
    onSuccess: () => { invalidate(); setEditingId(null); setForm(EMPTY_FORM); setApiError(null) },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail
      setApiError(typeof detail === "string" ? detail : "Update failed.")
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteRoutingOp(ecnId, itemId, id),
    onSuccess: () => { invalidate(); setConfirmDeleteId(null) },
  })

  function startAdd() {
    setEditingId(null)
    setForm({ ...EMPTY_FORM, operation_number: String((ops.length + 1) * 10) })
    setApiError(null)
    setAdding(true)
  }

  function startEdit(op: RoutingOp) {
    setAdding(false)
    setForm(opToForm(op))
    setApiError(null)
    setEditingId(op.id)
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
      const { operation_number: _, ...patchable } = formToBody(form)
      updateMut.mutate({ id: editingId, body: patchable })
    }
  }

  const isPending = createMut.isPending || updateMut.isPending || deleteMut.isPending

  return (
    <div className="space-y-3">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold text-neutral-500 uppercase tracking-wider">Routing Operations</p>
          <p className="text-xs text-neutral-400 mt-0.5">PDS002MI operations for {itemNumber}</p>
        </div>
        {!readOnly && !adding && !editingId && (
          <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={startAdd}>
            + Add operation
          </Button>
        )}
      </div>

      {/* Op list */}
      {isLoading ? (
        <div className="flex justify-center py-4"><Spinner size="sm" /></div>
      ) : ops.length === 0 && !adding ? (
        <p className="text-xs text-neutral-400 py-3 text-center">No routing operations defined.</p>
      ) : (
        <div className="divide-y divide-neutral-100 rounded-lg border border-neutral-200 overflow-hidden">
          {ops.map((op) =>
            editingId === op.id ? (
              <RoutingOpForm
                key={op.id}
                form={form}
                setForm={setForm}
                onSave={handleSave}
                onCancel={cancelForm}
                isPending={isPending}
                apiError={apiError}
                mode="edit"
              />
            ) : (
              <RoutingOpRow
                key={op.id}
                op={op}
                readOnly={readOnly}
                onEdit={() => startEdit(op)}
                onDelete={() => setConfirmDeleteId(op.id)}
                isPending={deleteMut.isPending && confirmDeleteId === op.id}
              />
            )
          )}
          {adding && (
            <RoutingOpForm
              form={form}
              setForm={setForm}
              onSave={handleSave}
              onCancel={cancelForm}
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
    </div>
  )
}

// ── Row ───────────────────────────────────────────────────────────────────────

function RoutingOpRow({
  op,
  readOnly,
  onEdit,
  onDelete,
  isPending,
}: {
  op: RoutingOp
  readOnly: boolean
  onEdit: () => void
  onDelete: () => void
  isPending: boolean
}) {
  return (
    <div className="group flex items-start gap-3 px-4 py-3 bg-white hover:bg-neutral-50 transition-colors duration-100">
      {/* Op number */}
      <span className="font-mono text-xs font-bold text-neutral-400 w-8 shrink-0 mt-0.5">
        {String(op.operation_number).padStart(3, "0")}
      </span>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-neutral-800 truncate">{op.operation_description}</span>
          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full shrink-0 ${CHANGE_TYPE_BADGE[op.change_type as ChangeType] ?? "bg-neutral-100 text-neutral-600"}`}>
            {op.change_type}
          </span>
        </div>
        <div className="flex gap-3 mt-1 text-xs text-neutral-500 flex-wrap">
          <span>WC: <span className="font-mono text-neutral-700">{op.work_centre}</span></span>
          <span>Run: <span className="font-mono text-neutral-700">{op.run_time}</span>h</span>
          {op.setup_time != null && (
            <span>Setup: <span className="font-mono text-neutral-700">{op.setup_time}</span>h</span>
          )}
          {op.movex_snapshot && (
            <span className="text-emerald-600 font-medium">Movex snapshot</span>
          )}
        </div>
      </div>

      {/* Actions — always rendered, hover toggles visibility */}
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

function RoutingOpForm({
  form,
  setForm,
  onSave,
  onCancel,
  isPending,
  apiError,
  mode,
}: {
  form: FormState
  setForm: (f: FormState) => void
  onSave: () => void
  onCancel: () => void
  isPending: boolean
  apiError: string | null
  mode: "add" | "edit"
}) {
  const set = (k: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [k]: e.target.value })

  const valid = isFormValid(form)

  return (
    <div className="bg-neutral-50/80 border-t border-neutral-100 first:border-t-0 px-4 py-4 space-y-3">
      <p className="text-xs font-semibold text-neutral-600">{mode === "add" ? "New operation" : "Edit operation"}</p>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-xs font-medium text-neutral-600">Op number <span className="text-red-500">*</span></Label>
          <Input
            type="number"
            min={1}
            value={form.operation_number}
            onChange={set("operation_number")}
            disabled={mode === "edit"}
            className="h-8 text-xs font-mono"
            placeholder="e.g. 10"
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

      <div className="space-y-1">
        <Label className="text-xs font-medium text-neutral-600">
          Description <span className="text-red-500">*</span>
          <span className={`ml-1 tabular-nums ${form.operation_description.length > 30 ? "text-red-500" : "text-neutral-400"}`}>
            ({form.operation_description.length}/30)
          </span>
        </Label>
        <Input
          value={form.operation_description}
          onChange={set("operation_description")}
          maxLength={30}
          className="h-8 text-xs"
          placeholder="e.g. SMT Assembly"
        />
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1">
          <Label className="text-xs font-medium text-neutral-600">Work centre <span className="text-red-500">*</span></Label>
          <Input
            value={form.work_centre}
            onChange={set("work_centre")}
            maxLength={8}
            className="h-8 text-xs font-mono uppercase"
            placeholder="e.g. SMT01"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs font-medium text-neutral-600">Run time (h) <span className="text-red-500">*</span></Label>
          <Input
            type="number"
            min={0}
            step={0.01}
            value={form.run_time}
            onChange={set("run_time")}
            className="h-8 text-xs font-mono"
            placeholder="0.50"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs font-medium text-neutral-600">Setup time (h)</Label>
          <Input
            type="number"
            min={0}
            step={0.01}
            value={form.setup_time}
            onChange={set("setup_time")}
            className="h-8 text-xs font-mono"
            placeholder="0.25"
          />
        </div>
      </div>

      {apiError && (
        <p className="text-xs text-red-600">{apiError}</p>
      )}

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={onCancel} disabled={isPending}>
          Cancel
        </Button>
        <Button
          type="button"
          size="sm"
          className="h-7 text-xs min-w-[80px]"
          onClick={handleSave}
          disabled={!valid || isPending}
        >
          {isPending ? <Spinner size="sm" /> : mode === "add" ? "Add" : "Save"}
        </Button>
      </div>
    </div>
  )

  function handleSave() {
    if (valid) onSave()
  }
}

// ── Delete confirmation ───────────────────────────────────────────────────────

function DeleteConfirm({
  onConfirm,
  onCancel,
  isPending,
}: {
  onConfirm: () => void
  onCancel: () => void
  isPending: boolean
}) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 flex items-center justify-between gap-3">
      <p className="text-xs text-red-700">Remove this routing operation?</p>
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
