import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Spinner } from "@/components/ui/spinner"
import {
  fetchMPNs, createMPN, updateMPN, deleteMPN,
  type MPN, type MPNBody,
} from "@/api/ecn"

// ── Options ───────────────────────────────────────────────────────────────────

const LIFECYCLE_OPTIONS = [
  { value: "", label: "— Not set —" },
  { value: "active", label: "Active" },
  { value: "eol", label: "End of Life" },
  { value: "nrnd", label: "Not Recommended for New Design" },
]

const PACKAGING_OPTIONS = [
  { value: "", label: "— Not set —" },
  { value: "tape_reel", label: "Tape & Reel" },
  { value: "tray", label: "Tray" },
  { value: "tube", label: "Tube" },
  { value: "cut_tape", label: "Cut Tape" },
]

interface MPNFormState {
  mpn: string
  manufacturer: string
  is_default: boolean
  msl_level: string
  lifecycle: string
  eol_date: string
  lead_time_weeks: string
  packaging_type: string
  do_not_buy: boolean
  alt_mpn: string
  notes: string
}

const EMPTY_MPN: MPNFormState = {
  mpn: "", manufacturer: "", is_default: false, msl_level: "",
  lifecycle: "", eol_date: "", lead_time_weeks: "", packaging_type: "",
  do_not_buy: false, alt_mpn: "", notes: "",
}

function mpnFormToBody(f: MPNFormState): MPNBody {
  return {
    mpn: f.mpn.trim(),
    manufacturer: f.manufacturer.trim() || null,
    is_default: f.is_default,
    msl_level: f.msl_level ? parseInt(f.msl_level, 10) : null,
    lifecycle: f.lifecycle || null,
    eol_date: f.eol_date || null,
    lead_time_weeks: f.lead_time_weeks ? parseInt(f.lead_time_weeks, 10) : null,
    packaging_type: f.packaging_type || null,
    do_not_buy: f.do_not_buy,
    alt_mpn: f.alt_mpn.trim() || null,
    notes: f.notes.trim() || null,
  }
}

function mpnToForm(m: MPN): MPNFormState {
  return {
    mpn: m.mpn,
    manufacturer: m.manufacturer ?? "",
    is_default: m.is_default,
    msl_level: m.msl_level != null ? String(m.msl_level) : "",
    lifecycle: m.lifecycle ?? "",
    eol_date: m.eol_date ?? "",
    lead_time_weeks: m.lead_time_weeks != null ? String(m.lead_time_weeks) : "",
    packaging_type: m.packaging_type ?? "",
    do_not_buy: m.do_not_buy,
    alt_mpn: m.alt_mpn ?? "",
    notes: m.notes ?? "",
  }
}

// ── Panel ─────────────────────────────────────────────────────────────────────

interface Props {
  ecnId: string
  itemId: string
  itemNumber: string
  readOnly?: boolean
}

export default function MPNsPanel({ ecnId, itemId, itemNumber, readOnly = false }: Props) {
  const qc = useQueryClient()
  const qKey = ["mpns", ecnId, itemId]
  const [adding, setAdding] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<MPNFormState>(EMPTY_MPN)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)

  const { data: mpns = [], isLoading } = useQuery({
    queryKey: qKey,
    queryFn: () => fetchMPNs(ecnId, itemId),
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: qKey })
    qc.invalidateQueries({ queryKey: ["ecn-item", ecnId, itemId] })
  }

  const createMut = useMutation({
    mutationFn: (body: MPNBody) => createMPN(ecnId, itemId, body),
    onSuccess: () => { invalidate(); setAdding(false); setForm(EMPTY_MPN); setApiError(null) },
    onError: (err: any) => {
      const d = err?.response?.data?.detail
      setApiError(typeof d === "string" ? d : "Save failed — MPN may already exist on this item.")
    },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<MPNBody> }) => updateMPN(ecnId, itemId, id, body),
    onSuccess: () => { invalidate(); setEditingId(null); setForm(EMPTY_MPN); setApiError(null) },
    onError: (err: any) => {
      const d = err?.response?.data?.detail
      setApiError(typeof d === "string" ? d : "Update failed.")
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteMPN(ecnId, itemId, id),
    onSuccess: () => { invalidate(); setConfirmDeleteId(null) },
  })

  function startAdd() {
    setEditingId(null)
    setForm(EMPTY_MPN)
    setApiError(null)
    setAdding(true)
  }

  function startEdit(m: MPN) {
    setAdding(false)
    setForm(mpnToForm(m))
    setApiError(null)
    setEditingId(m.id)
  }

  function cancelForm() {
    setAdding(false)
    setEditingId(null)
    setForm(EMPTY_MPN)
    setApiError(null)
  }

  function handleSave() {
    if (!form.mpn.trim()) return
    const body = mpnFormToBody(form)
    if (adding) {
      createMut.mutate(body)
    } else if (editingId) {
      updateMut.mutate({ id: editingId, body })
    }
  }

  const isPending = createMut.isPending || updateMut.isPending || deleteMut.isPending

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold text-neutral-500 uppercase tracking-wider">Manufacturer Part Numbers</p>
          <p className="text-xs text-neutral-400 mt-0.5">MPNs for {itemNumber}</p>
        </div>
        {!readOnly && !adding && !editingId && (
          <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={startAdd}>
            + Add MPN
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="flex justify-center py-4"><Spinner size="sm" /></div>
      ) : mpns.length === 0 && !adding ? (
        <p className="text-xs text-neutral-400 py-3 text-center">No MPNs defined for this item.</p>
      ) : (
        <div className="divide-y divide-neutral-100 rounded-lg border border-neutral-200 overflow-hidden">
          {mpns.map((m) =>
            editingId === m.id ? (
              <MPNForm
                key={m.id}
                form={form}
                setForm={setForm}
                onSave={handleSave}
                onCancel={cancelForm}
                isPending={isPending}
                apiError={apiError}
                mode="edit"
              />
            ) : (
              <MPNRow
                key={m.id}
                mpn={m}
                readOnly={readOnly}
                onEdit={() => startEdit(m)}
                onDelete={() => setConfirmDeleteId(m.id)}
                isPending={deleteMut.isPending && confirmDeleteId === m.id}
              />
            )
          )}
          {adding && (
            <MPNForm
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

      {confirmDeleteId && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 flex items-center justify-between gap-3">
          <p className="text-xs text-red-700">Remove this MPN?</p>
          <div className="flex gap-2 shrink-0">
            <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={() => setConfirmDeleteId(null)} disabled={deleteMut.isPending}>Cancel</Button>
            <Button type="button" size="sm" className="h-7 text-xs bg-red-600 hover:bg-red-700 text-white min-w-[70px]" onClick={() => deleteMut.mutate(confirmDeleteId!)} disabled={deleteMut.isPending}>
              {deleteMut.isPending ? <Spinner size="sm" /> : "Remove"}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Row ───────────────────────────────────────────────────────────────────────

function MPNRow({
  mpn: m,
  readOnly,
  onEdit,
  onDelete,
  isPending,
}: {
  mpn: MPN
  readOnly: boolean
  onEdit: () => void
  onDelete: () => void
  isPending: boolean
}) {
  return (
    <div className="group flex items-start gap-3 px-4 py-3 bg-white hover:bg-neutral-50 transition-colors duration-100">
      <div className="flex-1 min-w-0 space-y-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-sm font-semibold text-neutral-800">{m.mpn}</span>
          {m.is_default && (
            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-700 shrink-0">Default</span>
          )}
          {m.do_not_buy && (
            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-red-100 text-red-700 shrink-0">Do Not Buy</span>
          )}
          {m.lifecycle && m.lifecycle !== "active" && (
            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 shrink-0 uppercase">{m.lifecycle}</span>
          )}
        </div>
        <div className="flex gap-3 flex-wrap text-xs text-neutral-500">
          {m.manufacturer && <span>{m.manufacturer}</span>}
          {m.msl_level != null && <span>MSL {m.msl_level}</span>}
          {m.lead_time_weeks != null && <span>{m.lead_time_weeks}w lead</span>}
          {m.packaging_type && <span className="capitalize">{m.packaging_type.replace("_", " ")}</span>}
          {m.eol_date && <span>EOL: {m.eol_date}</span>}
          {m.alt_mpn && <span>Alt: <span className="font-mono">{m.alt_mpn}</span></span>}
        </div>
        {m.notes && <p className="text-xs text-neutral-400 italic">{m.notes}</p>}
      </div>
      {!readOnly && (
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-100 shrink-0">
          <button type="button" onClick={onEdit} className="text-xs text-neutral-500 hover:text-neutral-900 px-2 py-1 rounded hover:bg-neutral-100 transition-colors duration-100">Edit</button>
          <button type="button" onClick={onDelete} disabled={isPending} className="text-xs text-red-500 hover:text-red-700 px-2 py-1 rounded hover:bg-red-50 transition-colors duration-100 disabled:opacity-40">
            {isPending ? <Spinner size="sm" /> : "Remove"}
          </button>
        </div>
      )}
    </div>
  )
}

// ── Inline form ───────────────────────────────────────────────────────────────

function MPNForm({
  form,
  setForm,
  onSave,
  onCancel,
  isPending,
  apiError,
  mode,
}: {
  form: MPNFormState
  setForm: (f: MPNFormState) => void
  onSave: () => void
  onCancel: () => void
  isPending: boolean
  apiError: string | null
  mode: "add" | "edit"
}) {
  const set = (k: keyof MPNFormState) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [k]: e.target.value })

  const toggle = (k: "is_default" | "do_not_buy") => () =>
    setForm({ ...form, [k]: !form[k] })

  const valid = form.mpn.trim().length >= 1 && form.mpn.trim().length <= 30

  return (
    <div className="bg-neutral-50/80 border-t border-neutral-100 first:border-t-0 px-4 py-4 space-y-3">
      <p className="text-xs font-semibold text-neutral-600">{mode === "add" ? "New MPN" : "Edit MPN"}</p>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-xs font-medium text-neutral-600">MPN <span className="text-red-500">*</span></Label>
          <Input
            value={form.mpn}
            onChange={set("mpn")}
            maxLength={30}
            className="h-8 text-xs font-mono"
            placeholder="e.g. GRM155R71A104KA01D"
            disabled={mode === "edit"}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs font-medium text-neutral-600">Manufacturer</Label>
          <Input
            value={form.manufacturer}
            onChange={set("manufacturer")}
            maxLength={60}
            className="h-8 text-xs"
            placeholder="e.g. Murata"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-xs font-medium text-neutral-600">Lifecycle</Label>
          <select
            value={form.lifecycle}
            onChange={set("lifecycle")}
            className="h-8 w-full rounded-md border border-neutral-200 bg-white px-2 text-xs focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:ring-offset-1"
          >
            {LIFECYCLE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs font-medium text-neutral-600">Packaging</Label>
          <select
            value={form.packaging_type}
            onChange={set("packaging_type")}
            className="h-8 w-full rounded-md border border-neutral-200 bg-white px-2 text-xs focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:ring-offset-1"
          >
            {PACKAGING_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1">
          <Label className="text-xs font-medium text-neutral-600">MSL level</Label>
          <Input
            type="number"
            min={1}
            max={6}
            value={form.msl_level}
            onChange={set("msl_level")}
            className="h-8 text-xs font-mono"
            placeholder="1–6"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs font-medium text-neutral-600">Lead time (wks)</Label>
          <Input
            type="number"
            min={0}
            value={form.lead_time_weeks}
            onChange={set("lead_time_weeks")}
            className="h-8 text-xs font-mono"
            placeholder="e.g. 12"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs font-medium text-neutral-600">EOL date</Label>
          <Input
            type="date"
            value={form.eol_date}
            onChange={set("eol_date")}
            className="h-8 text-xs"
          />
        </div>
      </div>

      <div className="space-y-1">
        <Label className="text-xs font-medium text-neutral-600">Alternate MPN</Label>
        <Input
          value={form.alt_mpn}
          onChange={set("alt_mpn")}
          maxLength={100}
          className="h-8 text-xs font-mono"
          placeholder="Secondary / alternate part number"
        />
      </div>

      <div className="space-y-1">
        <Label className="text-xs font-medium text-neutral-600">Notes</Label>
        <Input
          value={form.notes}
          onChange={set("notes")}
          className="h-8 text-xs"
          placeholder="Optional notes"
        />
      </div>

      {/* Toggles */}
      <div className="flex gap-4">
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" className="sr-only" checked={form.is_default} onChange={toggle("is_default")} />
          <div className={`w-4 h-4 rounded border-2 flex items-center justify-center ${form.is_default ? "bg-blue-600 border-blue-600" : "border-neutral-300"}`}>
            {form.is_default && <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 12 12" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M2 6l3 3 5-5"/></svg>}
          </div>
          <span className="text-xs text-neutral-700">Default MPN</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" className="sr-only" checked={form.do_not_buy} onChange={toggle("do_not_buy")} />
          <div className={`w-4 h-4 rounded border-2 flex items-center justify-center ${form.do_not_buy ? "bg-red-600 border-red-600" : "border-neutral-300"}`}>
            {form.do_not_buy && <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 12 12" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M2 6l3 3 5-5"/></svg>}
          </div>
          <span className="text-xs text-neutral-700">Do Not Buy</span>
        </label>
      </div>

      {apiError && <p className="text-xs text-red-600">{apiError}</p>}

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={onCancel} disabled={isPending}>Cancel</Button>
        <Button type="button" size="sm" className="h-7 text-xs min-w-[80px]" onClick={onSave} disabled={!valid || isPending}>
          {isPending ? <Spinner size="sm" /> : mode === "add" ? "Add MPN" : "Save"}
        </Button>
      </div>
    </div>
  )
}
