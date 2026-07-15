import { useEffect, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Spinner } from "@/components/ui/spinner"
import {
  fetchItem, fetchGroups, createItem, updateItem, suggestPn,
  fetchMPNs, createMPN, updateMPN, deleteMPN, autofillItem,
  type MPN, type MPNBody, type AutofillResult,
} from "@/api/ecn"
import RoutingOpsPanel from "@/components/ecn/RoutingOpsPanel"

// ── Schema ────────────────────────────────────────────────────────────────────

const MOUNTING_TYPES = ["TH", "SMD", "MECHANICAL", "OTHER"] as const
const MOUNTING_TYPE_LABEL: Record<string, string> = {
  TH: "Through-hole (TH)",
  SMD: "Surface mount (SMD)",
  MECHANICAL: "Mechanical",
  OTHER: "Other",
}

const schema = z.object({
  item_number:        z.string().max(15).optional(),
  item_name:          z.string().max(30, "Max 30 characters").optional(),
  is_new_item:        z.boolean(),
  drawing_number:     z.string().max(30).optional(),
  procurement_group:  z.string().optional(),
  product_group:      z.string().optional(),
  mounting_type:      z.enum(["", "TH", "SMD", "MECHANICAL", "OTHER"]).optional(),
  customer_alias:     z.string().max(30).optional(),
  effectivity_type:   z.enum(["IMMEDIATE", "DATE", "ECN"]),
  effectivity_from:   z.string().optional(),
}).superRefine((data, ctx) => {
  if (!data.is_new_item && !data.item_number?.trim()) {
    ctx.addIssue({ code: "custom", path: ["item_number"], message: "Required for existing parts" })
  }
  if (data.effectivity_type === "DATE" && !data.effectivity_from?.trim()) {
    ctx.addIssue({ code: "custom", path: ["effectivity_from"], message: "Date is required when effectivity type is 'By date'" })
  }
})
type FormValues = z.infer<typeof schema>

// ── Tab type ──────────────────────────────────────────────────────────────────

type Tab = "details" | "routing" | "mpns"

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  ecnId: string
  itemId: string | null
  nextLineNumber: number
  customerNumber: string | null
  onClose: () => void
}

export default function ECNItemPanel({ ecnId, itemId, nextLineNumber, customerNumber, onClose }: Props) {
  const isNew = itemId === null
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>("details")
  const [descLen, setDescLen] = useState(0)
  const [pnError, setPnError] = useState<string | null>(null)
  const [pnLoading, setPnLoading] = useState(false)

  const { data: item } = useQuery({
    queryKey: ["ecn-item", ecnId, itemId],
    queryFn: () => fetchItem(ecnId, itemId!),
    enabled: !isNew && !!itemId,
  })

  const { data: groups = [] } = useQuery({
    queryKey: ["part-groups"],
    queryFn: fetchGroups,
  })

  const { data: mpns = [] } = useQuery({
    queryKey: ["mpns", ecnId, itemId],
    queryFn: () => fetchMPNs(ecnId, itemId!),
    enabled: !isNew && !!itemId,
  })
  const defaultMpn = mpns.find((m) => m.is_default)?.mpn ?? null

  const [autofillPreview, setAutofillPreview] = useState<AutofillResult | null>(null)
  const [autofillError, setAutofillError] = useState<string | null>(null)
  const [autofillLoading, setAutofillLoading] = useState(false)

  const prgpOptions = [...new Set(groups.map((g) => g.procurement_group))].sort()

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    reset,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { is_new_item: false, effectivity_type: "IMMEDIATE" },
  })

  useEffect(() => {
    if (item) {
      reset({
        item_number:       item.item_number ?? "",
        item_name:         item.item_name ?? "",
        is_new_item:       item.is_new_item ?? false,
        drawing_number:    item.drawing_number ?? "",
        procurement_group: item.procurement_group ?? "",
        product_group:     item.product_group ?? "",
        mounting_type:     item.mounting_type ?? "",
        customer_alias:    item.customer_alias ?? "",
        effectivity_type:  item.effectivity_type ?? "IMMEDIATE",
        effectivity_from:  item.effectivity_from ?? "",
      })
      setDescLen((item.item_name ?? "").length)
    }
  }, [item, reset])

  const watchedPrgp     = watch("procurement_group")
  const watchedItcl     = watch("product_group")
  const isNewItem       = watch("is_new_item")
  const effectivityType = watch("effectivity_type")

  const itclOptions = watchedPrgp
    ? [...new Set(groups.filter((g) => g.procurement_group === watchedPrgp).map((g) => g.product_group))].sort()
    : []

  const commodityCodes = watchedPrgp && watchedItcl
    ? groups.find((g) => g.procurement_group === watchedPrgp && g.product_group === watchedItcl)?.commodity_codes ?? []
    : []

  const saveMutation = useMutation({
    mutationFn: (data: FormValues) =>
      isNew
        ? createItem(ecnId, nextLineNumber, data as Record<string, unknown>)
        : updateItem(ecnId, itemId!, data as Record<string, unknown>),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ecn", ecnId] })
      qc.invalidateQueries({ queryKey: ["ecn-items", ecnId] })
      onClose()
    },
  })

  const handleSuggestPn = async () => {
    if (!watchedPrgp || !watchedItcl || !customerNumber) return
    setPnLoading(true)
    setPnError(null)
    try {
      const result = await suggestPn(ecnId, watchedPrgp, watchedItcl)
      setValue("item_number", result.suggested_pn, { shouldDirty: true })
    } catch {
      setPnError("Could not generate suggestion — Movex may be unavailable")
    } finally {
      setPnLoading(false)
    }
  }

  const watchedItemNumber = watch("item_number")

  const handleAutofill = async () => {
    if (!itemId || !defaultMpn) return
    setAutofillLoading(true)
    setAutofillError(null)
    setAutofillPreview(null)
    try {
      const result = await autofillItem(ecnId, itemId, watchedItemNumber ?? "")
      if (!result.item_name && !result.mounting_type && !result.unit_of_measure) {
        setAutofillError(`No supplier match found for ${defaultMpn}.`)
      } else {
        setAutofillPreview(result)
      }
    } catch {
      setAutofillError("Autofill lookup failed — please try again shortly.")
    } finally {
      setAutofillLoading(false)
    }
  }

  const applyAutofill = () => {
    if (!autofillPreview) return
    if (autofillPreview.item_name) {
      setValue("item_name", autofillPreview.item_name, { shouldDirty: true })
      setDescLen(autofillPreview.item_name.length)
    }
    if (autofillPreview.mounting_type) {
      setValue("mounting_type", autofillPreview.mounting_type as FormValues["mounting_type"], { shouldDirty: true })
    }
    setAutofillPreview(null)
  }

  const descOver   = descLen > 30
  const canSuggest = !!watchedPrgp && !!watchedItcl && !!customerNumber && !pnLoading

  const itemNumber = item?.item_number ?? (isNew ? "New item" : "")

  return (
    <Sheet open onOpenChange={(open) => { if (!open) onClose() }}>
      <SheetContent className="w-[520px] sm:w-[560px] flex flex-col overflow-hidden p-0 bg-white">

        <SheetHeader className="px-7 pt-6 pb-0 border-b bg-white shrink-0">
          <SheetTitle className="text-lg font-semibold">
            {isNew ? "Add item" : "Edit item"}
          </SheetTitle>
          <SheetDescription className="text-sm text-neutral-500 mt-0.5 mb-4">
            {isNew
              ? "Fill in the details below to add this part to the ECN."
              : (item?.item_number ? `Editing ${item.item_number}` : "Loading item…")}
          </SheetDescription>

          {/* Tab bar — only show for existing items */}
          {!isNew && (
            <div className="flex gap-0 -mb-px mt-2">
              {(["details", "routing", "mpns"] as Tab[]).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTab(t)}
                  className={`px-4 py-2.5 text-xs font-semibold border-b-2 transition-colors duration-150 capitalize ${
                    tab === t
                      ? "border-neutral-900 text-neutral-900"
                      : "border-transparent text-neutral-400 hover:text-neutral-600"
                  }`}
                >
                  {t === "routing" ? "Routing Ops" : t === "mpns" ? "MPNs" : "Details"}
                </button>
              ))}
            </div>
          )}
        </SheetHeader>

        {/* ── Details tab ── */}
        {(isNew || tab === "details") && (
          <form onSubmit={handleSubmit((d) => saveMutation.mutate(d))} className="flex flex-col flex-1 overflow-hidden">
            <div className="flex-1 overflow-y-auto px-7 py-6 space-y-6 bg-neutral-50/60">

              {/* New item toggle */}
              <label className={`flex items-start gap-4 rounded-xl border-2 px-5 py-4 cursor-pointer transition-all duration-150 ${
                isNewItem ? "border-blue-400 bg-blue-50" : "border-neutral-200 bg-white hover:border-neutral-300"
              }`}>
                <input type="checkbox" className="sr-only" {...register("is_new_item")} />
                <div className={`mt-0.5 w-5 h-5 rounded-md border-2 flex items-center justify-center shrink-0 transition-colors duration-150 ${
                  isNewItem ? "bg-blue-600 border-blue-600 text-white" : "border-neutral-300 bg-white"
                }`}>
                  {isNewItem && (
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 12 12" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M2 6l3 3 5-5" />
                    </svg>
                  )}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-neutral-800">New item (no Movex record)</p>
                  <p className="text-xs text-neutral-500 mt-0.5 leading-relaxed">
                    Check this if the part doesn't exist in Movex yet. A part number will be created during implementation.
                  </p>
                </div>
              </label>

              {/* Identification */}
              <FieldSection title="Identification" subtitle="Part number and description">
                <Field label="Item number">
                  <div className="flex gap-2">
                    <Input
                      id="item_number"
                      placeholder={isNewItem ? "Leave blank to auto-generate" : "e.g. LFSC691234"}
                      className="font-mono h-10 flex-1 text-sm"
                      {...register("item_number")}
                    />
                    {isNewItem && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-10 shrink-0 min-w-[100px] text-xs"
                        disabled={!canSuggest}
                        onClick={handleSuggestPn}
                        title={canSuggest ? "Suggest next available part number" : "Complete the required fields below first"}
                      >
                        {pnLoading ? <Spinner size="sm" /> : "Suggest PN"}
                      </Button>
                    )}
                  </div>
                  {pnError && <FieldError>{pnError}</FieldError>}
                  {isNewItem && !canSuggest && !pnLoading && (
                    <FieldHint>
                      Suggest PN needs:{" "}
                      {[
                        !customerNumber && "a customer set on the ECN",
                        !watchedPrgp && "Procurement group",
                        !watchedItcl && "Product group",
                      ].filter(Boolean).join(", ")}
                    </FieldHint>
                  )}
                  {!isNewItem && <FieldHint>Must match an existing Movex part number</FieldHint>}
                </Field>

                {isNewItem && (
                  <Field label="Drawing number" hint="Required before DC approval">
                    <Input
                      id="drawing_number"
                      placeholder="e.g. DRW-00123"
                      className="h-10 text-sm font-mono"
                      {...register("drawing_number")}
                    />
                  </Field>
                )}

                <Field
                  label="Description"
                  labelRight={
                    <span className={`text-xs tabular-nums transition-colors duration-150 ${descOver ? "text-red-500 font-semibold" : "text-neutral-400"}`}>
                      {descLen}/30
                    </span>
                  }
                >
                  <Input
                    id="item_name"
                    placeholder="Short description — maps to Movex MITMAS.MMITDS"
                    className={`h-10 text-sm ${descOver ? "border-red-400 focus-visible:ring-red-400" : ""}`}
                    maxLength={35}
                    {...register("item_name", { onChange: (e) => setDescLen(e.target.value.length) })}
                  />
                  {errors.item_name
                    ? <FieldError>{errors.item_name.message}</FieldError>
                    : <FieldHint>Maximum 30 characters</FieldHint>
                  }
                </Field>

                {!isNew && (
                  <div className="pt-1">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-8 text-xs"
                      disabled={!defaultMpn || autofillLoading}
                      onClick={handleAutofill}
                      title={defaultMpn ? `Look up ${defaultMpn} via DigiKey/Nexar` : "Set a default MPN on the MPNs tab first"}
                    >
                      {autofillLoading
                        ? <><Spinner size="sm" /><span className="ml-1.5">Looking up…</span></>
                        : "Autofill from MPN"
                      }
                    </Button>
                    {!defaultMpn && (
                      <FieldHint>Set a default MPN on the MPNs tab to enable autofill</FieldHint>
                    )}
                    {autofillError && <FieldError>{autofillError}</FieldError>}

                    {autofillPreview && (
                      <div className="mt-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 space-y-2">
                        <p className="text-xs font-semibold text-blue-800">
                          Supplier data found for {defaultMpn} — review before applying:
                        </p>
                        <dl className="text-xs text-blue-900 space-y-1">
                          {autofillPreview.item_name && (
                            <div className="flex gap-2">
                              <dt className="font-medium shrink-0">Description:</dt>
                              <dd className="truncate">{autofillPreview.item_name}</dd>
                            </div>
                          )}
                          {autofillPreview.mounting_type && (
                            <div className="flex gap-2">
                              <dt className="font-medium shrink-0">Mounting type:</dt>
                              <dd>{MOUNTING_TYPE_LABEL[autofillPreview.mounting_type] ?? autofillPreview.mounting_type}</dd>
                            </div>
                          )}
                          {autofillPreview.unit_of_measure && (
                            <div className="flex gap-2">
                              <dt className="font-medium shrink-0">Unit of measure:</dt>
                              <dd>{autofillPreview.unit_of_measure}</dd>
                            </div>
                          )}
                        </dl>
                        <div className="flex justify-end gap-2 pt-1">
                          <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={() => setAutofillPreview(null)}>
                            Discard
                          </Button>
                          <Button type="button" size="sm" className="h-7 text-xs" onClick={applyAutofill}>
                            Apply to form
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </FieldSection>

              {/* Classification */}
              <FieldSection title="Classification" subtitle="Procurement and product group">
                <Field label="Procurement group">
                  <select
                    id="procurement_group"
                    className="h-10 w-full rounded-md border border-neutral-200 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:ring-offset-1 transition-shadow duration-150"
                    {...register("procurement_group")}
                    onChange={(e) => {
                      setValue("procurement_group", e.target.value, { shouldDirty: true })
                      setValue("product_group", "", { shouldDirty: true })
                    }}
                  >
                    <option value="">— Select procurement group —</option>
                    {prgpOptions.map((p) => <option key={p} value={p}>{p}</option>)}
                  </select>
                </Field>

                <Field label="Product group">
                  <select
                    id="product_group"
                    className="h-10 w-full rounded-md border border-neutral-200 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed transition-shadow duration-150"
                    disabled={!watchedPrgp}
                    {...register("product_group")}
                  >
                    <option value="">— Select product group —</option>
                    {itclOptions.map((p) => <option key={p} value={p}>{p}</option>)}
                  </select>
                  {!watchedPrgp && <FieldHint>Select a procurement group first</FieldHint>}
                  {commodityCodes.length > 0 && (
                    <FieldHint>
                      Commodity code{commodityCodes.length > 1 ? "s" : ""}:{" "}
                      <span className="font-mono text-neutral-600">{commodityCodes.join(", ")}</span>
                    </FieldHint>
                  )}
                </Field>

                <Field label="Mounting type" hint="Auto-filled from DigiKey when available; set manually otherwise">
                  <select
                    id="mounting_type"
                    className="h-10 w-full rounded-md border border-neutral-200 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:ring-offset-1 transition-shadow duration-150"
                    {...register("mounting_type")}
                  >
                    <option value="">— Not set —</option>
                    {MOUNTING_TYPES.map((mt) => (
                      <option key={mt} value={mt}>{MOUNTING_TYPE_LABEL[mt]}</option>
                    ))}
                  </select>
                </Field>
              </FieldSection>

              {/* Effectivity */}
              <FieldSection title="Effectivity" subtitle="When this change takes effect">
                <Field label="Effectivity type">
                  <select
                    id="effectivity_type"
                    className="h-10 w-full rounded-md border border-neutral-200 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:ring-offset-1"
                    {...register("effectivity_type")}
                  >
                    <option value="IMMEDIATE">Immediate — apply as soon as approved</option>
                    <option value="DATE">By date — specify effective date</option>
                    <option value="ECN">By ECN number</option>
                  </select>
                </Field>
                {effectivityType === "DATE" && (
                  <Field label="Effective from">
                    <Input
                      id="effectivity_from"
                      type="date"
                      className="h-10 text-sm"
                      {...register("effectivity_from")}
                    />
                    {errors.effectivity_from && <FieldError>{errors.effectivity_from.message}</FieldError>}
                  </Field>
                )}
              </FieldSection>

              {/* Optional */}
              <FieldSection title="Optional" subtitle="Additional references">
                <Field label="Customer alias" hint="Customer part number or cross-reference">
                  <Input
                    id="customer_alias"
                    placeholder="e.g. CUST-PN-00012"
                    className="h-10 text-sm"
                    {...register("customer_alias")}
                  />
                </Field>
              </FieldSection>

            </div>

            {/* Footer */}
            <div className="shrink-0 border-t bg-white px-7 py-4 flex items-center justify-between gap-4">
              <div className="flex-1">
                {saveMutation.isError && (
                  <p className="text-xs text-red-600">Save failed — please try again.</p>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Button type="button" variant="outline" size="sm" onClick={onClose}>
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  className="min-w-[90px]"
                  disabled={isSubmitting || saveMutation.isPending || (!isDirty && !isNew)}
                >
                  {saveMutation.isPending
                    ? <><Spinner size="sm" /><span className="ml-1.5">Saving…</span></>
                    : "Save item"
                  }
                </Button>
              </div>
            </div>
          </form>
        )}

        {/* ── Routing Ops tab ── */}
        {!isNew && tab === "routing" && itemId && (
          <div className="flex-1 overflow-y-auto px-7 py-6 bg-neutral-50/60">
            <RoutingOpsPanel
              ecnId={ecnId}
              itemId={itemId}
              itemNumber={itemNumber}
            />
          </div>
        )}

        {/* ── MPNs tab ── */}
        {!isNew && tab === "mpns" && itemId && (
          <div className="flex-1 overflow-y-auto px-7 py-6 bg-neutral-50/60">
            <MPNsPanel ecnId={ecnId} itemId={itemId} itemNumber={itemNumber} />
          </div>
        )}

      </SheetContent>
    </Sheet>
  )
}

// ── MPN Panel (S8-B) ──────────────────────────────────────────────────────────

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

function MPNsPanel({ ecnId, itemId, itemNumber }: { ecnId: string; itemId: string; itemNumber: string }) {
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
        {!adding && !editingId && (
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

function MPNRow({
  mpn: m,
  onEdit,
  onDelete,
  isPending,
}: {
  mpn: MPN
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
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-100 shrink-0">
        <button type="button" onClick={onEdit} className="text-xs text-neutral-500 hover:text-neutral-900 px-2 py-1 rounded hover:bg-neutral-100 transition-colors duration-100">Edit</button>
        <button type="button" onClick={onDelete} disabled={isPending} className="text-xs text-red-500 hover:text-red-700 px-2 py-1 rounded hover:bg-red-50 transition-colors duration-100 disabled:opacity-40">
          {isPending ? <Spinner size="sm" /> : "Remove"}
        </button>
      </div>
    </div>
  )
}

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

// ── Layout helpers (local to this panel) ─────────────────────────────────────

function FieldSection({ title, subtitle, children }: {
  title: string; subtitle?: string; children: React.ReactNode
}) {
  return (
    <div className="bg-white rounded-xl border border-neutral-200 overflow-hidden shadow-sm">
      <div className="px-5 py-3.5 border-b border-neutral-100 bg-neutral-50/80">
        <p className="text-xs font-semibold text-neutral-500 uppercase tracking-wider">{title}</p>
        {subtitle && <p className="text-xs text-neutral-400 mt-0.5">{subtitle}</p>}
      </div>
      <div className="px-5 py-4 space-y-4">{children}</div>
    </div>
  )
}

function Field({ label, hint, labelRight, children }: {
  label: string; hint?: string; labelRight?: React.ReactNode; children: React.ReactNode
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <Label className="text-sm font-medium text-neutral-700">{label}</Label>
        {labelRight}
      </div>
      {children}
      {hint && <FieldHint>{hint}</FieldHint>}
    </div>
  )
}

function FieldHint({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-neutral-400 leading-relaxed">{children}</p>
}

function FieldError({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-red-500">{children}</p>
}
