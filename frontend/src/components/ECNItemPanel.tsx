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
import axiosInstance from "@/api/axios"

// ── Types ─────────────────────────────────────────────────────────────────────

interface GroupEntry {
  procurement_group: string
  product_group: string
  commodity_codes: string[]
}

interface SuggestPnResponse {
  suggested_pn: string
  commodity_code: string
  sequence: number
  prefix: string
}

// ── Schema ────────────────────────────────────────────────────────────────────

const schema = z.object({
  item_number:        z.string().max(15).optional(),
  item_name:          z.string().max(30, "Max 30 characters").optional(),
  is_new_item:        z.boolean(),
  procurement_group:  z.string().optional(),
  product_group:      z.string().optional(),
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

// ── API ───────────────────────────────────────────────────────────────────────

async function fetchItem(ecnId: string, itemId: string) {
  const { data } = await axiosInstance.get(`/api/v1/ecn/${ecnId}/items/${itemId}`)
  return data
}

async function fetchGroups() {
  const { data } = await axiosInstance.get("/api/v1/parts/groups")
  return data as GroupEntry[]
}

function stripEmpty<T extends Record<string, unknown>>(obj: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(obj).filter(([, v]) => v !== "" && v !== undefined)
  ) as Partial<T>
}

async function createItem(ecnId: string, lineNumber: number, body: FormValues) {
  const { data } = await axiosInstance.post(`/api/v1/ecn/${ecnId}/items`, {
    ...stripEmpty(body as Record<string, unknown>),
    line_number: lineNumber,
  })
  return data
}

async function updateItem(ecnId: string, itemId: string, body: Partial<FormValues>) {
  const { data } = await axiosInstance.patch(
    `/api/v1/ecn/${ecnId}/items/${itemId}`,
    stripEmpty(body as Record<string, unknown>),
  )
  return data
}

async function suggestPn(prgp: string, itcl: string): Promise<SuggestPnResponse> {
  const { data } = await axiosInstance.get(`/api/v1/parts/suggest-pn?prgp=${prgp}&itcl=${itcl}`)
  return data
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  ecnId: string
  itemId: string | null  // null = new item
  nextLineNumber: number
  onClose: () => void
}

export default function ECNItemPanel({ ecnId, itemId, nextLineNumber, onClose }: Props) {
  const isNew = itemId === null
  const qc = useQueryClient()
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
        procurement_group: item.procurement_group ?? "",
        product_group:     item.product_group ?? "",
        customer_alias:    item.customer_alias ?? "",
        effectivity_type:  item.effectivity_type ?? "IMMEDIATE",
        effectivity_from:  item.effectivity_from ?? "",
      })
      setDescLen((item.item_name ?? "").length)
    }
  }, [item, reset])

  const watchedPrgp        = watch("procurement_group")
  const watchedItcl        = watch("product_group")
  const isNewItem          = watch("is_new_item")
  const effectivityType    = watch("effectivity_type")

  const itclOptions = watchedPrgp
    ? [...new Set(groups.filter((g) => g.procurement_group === watchedPrgp).map((g) => g.product_group))].sort()
    : []

  const commodityCodes = watchedPrgp && watchedItcl
    ? groups.find((g) => g.procurement_group === watchedPrgp && g.product_group === watchedItcl)?.commodity_codes ?? []
    : []

  const saveMutation = useMutation({
    mutationFn: (data: FormValues) =>
      isNew ? createItem(ecnId, nextLineNumber, data) : updateItem(ecnId, itemId!, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ecn", ecnId] })
      qc.invalidateQueries({ queryKey: ["ecn-items", ecnId] })
      onClose()
    },
  })

  const handleSuggestPn = async () => {
    if (!watchedPrgp || !watchedItcl) return
    setPnLoading(true)
    setPnError(null)
    try {
      const result = await suggestPn(watchedPrgp, watchedItcl)
      setValue("item_number", result.suggested_pn, { shouldDirty: true })
    } catch {
      setPnError("Could not generate suggestion — Movex may be unavailable")
    } finally {
      setPnLoading(false)
    }
  }

  const descOver   = descLen > 30
  const canSuggest = !!watchedPrgp && !!watchedItcl && !pnLoading

  return (
    <Sheet open onOpenChange={(open) => { if (!open) onClose() }}>
      <SheetContent className="w-[480px] sm:w-[520px] flex flex-col overflow-hidden p-0 bg-white">

        {/* Header */}
        <SheetHeader className="px-7 pt-6 pb-5 border-b bg-white shrink-0">
          <SheetTitle className="text-lg font-semibold">
            {isNew ? "Add item" : "Edit item"}
          </SheetTitle>
          <SheetDescription className="text-sm text-neutral-500 mt-0.5">
            {isNew
              ? "Fill in the details below to add this part to the ECN."
              : (item?.item_number ? `Editing ${item.item_number}` : "Loading item…")}
          </SheetDescription>
        </SheetHeader>

        <form onSubmit={handleSubmit((d) => saveMutation.mutate(d))} className="flex flex-col flex-1 overflow-hidden">

          {/* Scrollable body */}
          <div className="flex-1 overflow-y-auto px-7 py-6 space-y-6 bg-neutral-50/60">

            {/* ── New item toggle ────────────────────────────────────────── */}
            <label className={`flex items-start gap-4 rounded-xl border-2 px-5 py-4 cursor-pointer transition-all duration-150 ${
              isNewItem
                ? "border-blue-400 bg-blue-50"
                : "border-neutral-200 bg-white hover:border-neutral-300"
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

            {/* ── Identification ─────────────────────────────────────────── */}
            <FieldSection title="Identification" subtitle="Part number and description">
              {/* Item number */}
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
                      title={canSuggest ? "Suggest next available part number" : "Select procurement and product group first"}
                    >
                      {pnLoading ? <Spinner size="sm" /> : "Suggest PN"}
                    </Button>
                  )}
                </div>
                {pnError && <FieldError>{pnError}</FieldError>}
                {!isNewItem && (
                  <FieldHint>Must match an existing Movex part number</FieldHint>
                )}
              </Field>

              {/* Description */}
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
                  {...register("item_name", {
                    onChange: (e) => setDescLen(e.target.value.length),
                  })}
                />
                {errors.item_name
                  ? <FieldError>{errors.item_name.message}</FieldError>
                  : <FieldHint>Maximum 30 characters</FieldHint>
                }
              </Field>
            </FieldSection>

            {/* ── Classification ─────────────────────────────────────────── */}
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
                {!watchedPrgp && (
                  <FieldHint>Select a procurement group first</FieldHint>
                )}
                {commodityCodes.length > 0 && (
                  <FieldHint>
                    Commodity code{commodityCodes.length > 1 ? "s" : ""}:{" "}
                    <span className="font-mono text-neutral-600">{commodityCodes.join(", ")}</span>
                  </FieldHint>
                )}
              </Field>
            </FieldSection>

            {/* ── Effectivity ────────────────────────────────────────────── */}
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
                  {errors.effectivity_from && (
                    <FieldError>{errors.effectivity_from.message}</FieldError>
                  )}
                </Field>
              )}
            </FieldSection>

            {/* ── Optional ───────────────────────────────────────────────── */}
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

          {/* ── Footer ─────────────────────────────────────────────────────── */}
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
      </SheetContent>
    </Sheet>
  )
}

// ── Layout helpers ────────────────────────────────────────────────────────────

function FieldSection({ title, subtitle, children }: {
  title: string
  subtitle?: string
  children: React.ReactNode
}) {
  return (
    <div className="bg-white rounded-xl border border-neutral-200 overflow-hidden shadow-sm">
      <div className="px-5 py-3.5 border-b border-neutral-100 bg-neutral-50/80">
        <p className="text-xs font-semibold text-neutral-500 uppercase tracking-wider">{title}</p>
        {subtitle && <p className="text-xs text-neutral-400 mt-0.5">{subtitle}</p>}
      </div>
      <div className="px-5 py-4 space-y-4">
        {children}
      </div>
    </div>
  )
}

function Field({ label, hint, labelRight, children }: {
  label: string
  hint?: string
  labelRight?: React.ReactNode
  children: React.ReactNode
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
