import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Spinner } from "@/components/ui/spinner"
import { createMPN, type MPNBody } from "@/api/ecn"

/**
 * ADR-016 — add an MPN change from the ECN-wide MPNs tab, with no item on the
 * ECN required.
 *
 * Before this, an MPN could only be authored through an ecn_items row
 * (ecn_mpns.ecn_item_id was NOT NULL), so an ECN that only adds a
 * manufacturer part had to carry a dummy item row telling reviewers the item
 * master was changing when it was not. Stargile never worked this way:
 * ZECNMPNI's primary key is (CMCONO, CMZECNID, CMITNO, CMMSEQ) — the item
 * number is IN the key, with no pointer to the items table.
 *
 * Mirrors AddBomChangeDrawer, minus the ERP browse: there is no live "current
 * MPN list" to pick from in M3 (Movex has no native MPN field — MPNs are
 * Oskar-owned, per ai/memory/05-stargile-ecn-reference.md:147). An MPN picker
 * over Oskar's own item_mpns master is the natural follow-up.
 */

interface FormState {
  item_number: string
  mpn: string
  manufacturer: string
  is_default: boolean
  lifecycle: string
  lead_time_weeks: string
  packaging_type: string
  do_not_buy: boolean
  alt_mpn: string
  notes: string
}

const EMPTY_FORM: FormState = {
  item_number: "",
  mpn: "",
  manufacturer: "",
  is_default: false,
  lifecycle: "",
  lead_time_weeks: "",
  packaging_type: "",
  do_not_buy: false,
  alt_mpn: "",
  notes: "",
}

const LIFECYCLES = ["", "active", "eol", "nrnd"] as const
const PACKAGING = ["", "tape_reel", "tray", "tube", "cut_tape"] as const

const PACKAGING_LABEL: Record<string, string> = {
  "": "—",
  tape_reel: "Tape & reel",
  tray: "Tray",
  tube: "Tube",
  cut_tape: "Cut tape",
}

/** Minimal shape of the axios errors this component reacts to. Avoids `any`,
 * which the lint config rejects. */
interface ApiError {
  response?: { status?: number; data?: { detail?: unknown } }
}

function formToBody(f: FormState): MPNBody & { item_number: string } {
  return {
    item_number: f.item_number.trim().toUpperCase(),
    mpn: f.mpn.trim(),
    manufacturer: f.manufacturer.trim() || null,
    is_default: f.is_default,
    lifecycle: f.lifecycle || null,
    lead_time_weeks: f.lead_time_weeks.trim()
      ? parseInt(f.lead_time_weeks, 10)
      : null,
    packaging_type: f.packaging_type || null,
    do_not_buy: f.do_not_buy,
    alt_mpn: f.alt_mpn.trim() || null,
    notes: f.notes.trim() || null,
  }
}

function isFormValid(f: FormState): boolean {
  return f.item_number.trim().length > 0 && f.mpn.trim().length > 0
}

interface Props {
  ecnId: string
  open: boolean
  onClose: () => void
  onSuccess?: () => void
}

export default function AddMpnDrawer({ ecnId, open, onClose, onSuccess }: Props) {
  const qc = useQueryClient()
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [apiError, setApiError] = useState<string | null>(null)
  const [lastAdded, setLastAdded] = useState<string | null>(null)

  const createMut = useMutation({
    mutationFn: (body: MPNBody & { item_number: string }) =>
      createMPN(ecnId, null, body),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["ecn-mpns-all", ecnId] })
      setLastAdded(created.mpn)
      // Keep the item number: adding several MPNs to one item is the common
      // case, and retyping it every time is the friction this drawer exists
      // to remove.
      setForm({ ...EMPTY_FORM, item_number: form.item_number })
      setApiError(null)
      onSuccess?.()
    },
    onError: (err: ApiError) => {
      const detail = err?.response?.data?.detail
      setApiError(
        typeof detail === "string"
          ? detail
          : "Save failed — check the fields below.",
      )
    },
  })

  if (!open) return null

  const set =
    (k: keyof FormState) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
      setForm((f) => ({ ...f, [k]: e.target.value }))

  const toggle = (k: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.checked }))

  const valid = isFormValid(form)

  return (
    <div className="fixed inset-0 z-[1050] flex justify-end bg-black/30" onClick={onClose}>
      <div
        className="w-full max-w-2xl h-full overflow-y-auto bg-white shadow-xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-white border-b border-neutral-200 px-6 py-4 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-neutral-900">Add MPN</h2>
            <p className="text-xs text-neutral-500 mt-0.5">
              Name the item directly — it does not need to be on this ECN.
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
              Added <span className="font-mono">{lastAdded}</span>. Add another below, or close.
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
                placeholder="LF200010"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs font-medium text-neutral-600">
                MPN <span className="text-red-500">*</span>
              </Label>
              <Input
                value={form.mpn}
                onChange={set("mpn")}
                className="h-8 text-xs font-mono"
                placeholder="CRCW060310K0FKEA"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs font-medium text-neutral-600">Manufacturer</Label>
              <Input
                value={form.manufacturer}
                onChange={set("manufacturer")}
                className="h-8 text-xs"
                placeholder="Vishay"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs font-medium text-neutral-600">Alternate MPN</Label>
              <Input
                value={form.alt_mpn}
                onChange={set("alt_mpn")}
                className="h-8 text-xs font-mono"
              />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1">
              <Label className="text-xs font-medium text-neutral-600">Lifecycle</Label>
              <select
                value={form.lifecycle}
                onChange={set("lifecycle")}
                className="h-8 w-full rounded-md border border-neutral-200 bg-white px-2 text-xs focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:ring-offset-1"
              >
                {LIFECYCLES.map((l) => (
                  <option key={l} value={l}>{l === "" ? "—" : l}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs font-medium text-neutral-600">Packaging</Label>
              <select
                value={form.packaging_type}
                onChange={set("packaging_type")}
                className="h-8 w-full rounded-md border border-neutral-200 bg-white px-2 text-xs focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:ring-offset-1"
              >
                {PACKAGING.map((p) => (
                  <option key={p} value={p}>{PACKAGING_LABEL[p]}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs font-medium text-neutral-600">Lead time (weeks)</Label>
              <Input
                type="number"
                min={0}
                value={form.lead_time_weeks}
                onChange={set("lead_time_weeks")}
                className="h-8 text-xs font-mono"
              />
            </div>
          </div>

          <div className="flex items-center gap-5 pt-1">
            <label className="flex items-center gap-2 text-xs text-neutral-700">
              <input type="checkbox" checked={form.is_default} onChange={toggle("is_default")} />
              Default MPN for this item
            </label>
            <label className="flex items-center gap-2 text-xs text-neutral-700">
              <input type="checkbox" checked={form.do_not_buy} onChange={toggle("do_not_buy")} />
              Do not buy
            </label>
          </div>
          <p className="text-[10px] text-neutral-400 -mt-2">
            Only one MPN per item can be the default — saving a second one is rejected.
          </p>

          <div className="space-y-1">
            <Label className="text-xs font-medium text-neutral-600">Notes</Label>
            <textarea
              value={form.notes}
              onChange={set("notes")}
              rows={2}
              className="w-full rounded-md border border-neutral-200 bg-white px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:ring-offset-1"
            />
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
            className="h-8 text-xs min-w-[90px]"
            onClick={() => createMut.mutate(formToBody(form))}
            disabled={!valid || createMut.isPending}
          >
            {createMut.isPending ? <Spinner size="sm" /> : "Add MPN"}
          </Button>
        </div>
      </div>
    </div>
  )
}
