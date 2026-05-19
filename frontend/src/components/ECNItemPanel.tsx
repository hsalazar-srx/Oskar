import { useEffect, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
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

// ── Schemas ───────────────────────────────────────────────────────────────────

const schema = z.object({
  item_number: z.string().max(15).optional(),
  item_name: z.string().max(30, "Max 30 characters").optional(),
  is_new_item: z.boolean(),
  procurement_group: z.string().optional(),
  product_group: z.string().optional(),
  customer_alias: z.string().max(30).optional(),
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

async function createItem(ecnId: string, body: FormValues) {
  const { data } = await axiosInstance.post(`/api/v1/ecn/${ecnId}/items/`, body)
  return data
}

async function updateItem(ecnId: string, itemId: string, body: Partial<FormValues>) {
  const { data } = await axiosInstance.patch(`/api/v1/ecn/${ecnId}/items/${itemId}`, body)
  return data
}

async function suggestPn(prgp: string, itcl: string): Promise<SuggestPnResponse> {
  const { data } = await axiosInstance.get(
    `/api/v1/parts/suggest-pn?prgp=${prgp}&itcl=${itcl}`,
  )
  return data
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  ecnId: string
  itemId: string | null   // null = new item
  onClose: () => void
}

export default function ECNItemPanel({ ecnId, itemId, onClose }: Props) {
  const isNew = itemId === null
  const qc = useQueryClient()
  const [descLen, setDescLen] = useState(0)
  const [pnSuggestion, setPnSuggestion] = useState<string | null>(null)
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
    defaultValues: { is_new_item: false },
  })

  // Populate form when editing existing item
  useEffect(() => {
    if (item) {
      reset({
        item_number: item.item_number ?? "",
        item_name: item.item_name ?? "",
        is_new_item: item.is_new_item ?? false,
        procurement_group: item.procurement_group ?? "",
        product_group: item.product_group ?? "",
        customer_alias: item.customer_alias ?? "",
      })
      setDescLen((item.item_name ?? "").length)
    }
  }, [item, reset])

  const watchedPrgp = watch("procurement_group")
  const watchedItcl = watch("product_group")
  const watchedName = watch("item_name") ?? ""

  // Filter product groups based on selected procurement group
  const itclOptions = watchedPrgp
    ? [...new Set(groups.filter((g) => g.procurement_group === watchedPrgp).map((g) => g.product_group))].sort()
    : []

  const saveMutation = useMutation({
    mutationFn: (data: FormValues) =>
      isNew ? createItem(ecnId, data) : updateItem(ecnId, itemId!, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ecn", ecnId] })
      onClose()
    },
  })

  const handleSuggestPn = async () => {
    if (!watchedPrgp || !watchedItcl) return
    setPnLoading(true)
    try {
      const result = await suggestPn(watchedPrgp, watchedItcl)
      setPnSuggestion(result.suggested_pn)
      setValue("item_number", result.suggested_pn, { shouldDirty: true })
    } catch {
      setPnSuggestion(null)
    } finally {
      setPnLoading(false)
    }
  }

  const onSubmit = (data: FormValues) => saveMutation.mutate(data)

  return (
    <Sheet open onOpenChange={(open) => { if (!open) onClose() }}>
      <SheetContent className="w-[420px] sm:w-[480px] overflow-y-auto">
        <SheetHeader className="mb-5">
          <SheetTitle>{isNew ? "Add item" : "Edit item"}</SheetTitle>
        </SheetHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
          {/* New item toggle */}
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" {...register("is_new_item")} />
            New item (no existing Movex record)
          </label>

          {/* Item number + suggest button */}
          <div className="space-y-1.5">
            <Label htmlFor="item_number">Item number</Label>
            <div className="flex gap-2">
              <Input
                id="item_number"
                placeholder="e.g. LFSC691234"
                className="font-mono"
                {...register("item_number")}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!watchedPrgp || !watchedItcl || pnLoading}
                onClick={handleSuggestPn}
                title="Suggest next available part number"
              >
                {pnLoading ? "…" : "Suggest"}
              </Button>
            </div>
            {pnSuggestion && (
              <p className="text-xs text-neutral-500">Suggested: <span className="font-mono">{pnSuggestion}</span></p>
            )}
          </div>

          {/* Item name / description */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="item_name">Item description</Label>
              <span className={`text-xs ${descLen > 30 ? "text-red-500" : "text-neutral-400"}`}>
                {descLen}/30
              </span>
            </div>
            <Input
              id="item_name"
              placeholder="Max 30 characters (Movex MITMAS.MMITDS)"
              maxLength={35}
              {...register("item_name", {
                onChange: (e) => setDescLen(e.target.value.length),
              })}
            />
            {errors.item_name && (
              <p className="text-xs text-red-500">{errors.item_name.message}</p>
            )}
            {watchedName.length > 0 && watchedName.length <= 30 && (
              <p className="text-xs text-neutral-400 font-mono">{watchedName}</p>
            )}
          </div>

          {/* Procurement group */}
          <div className="space-y-1.5">
            <Label htmlFor="procurement_group">Procurement group</Label>
            <select
              id="procurement_group"
              className="w-full rounded-md border border-neutral-200 bg-white px-3 py-2 text-sm"
              {...register("procurement_group")}
              onChange={(e) => {
                setValue("procurement_group", e.target.value, { shouldDirty: true })
                setValue("product_group", "", { shouldDirty: true })
              }}
            >
              <option value="">— Select —</option>
              {prgpOptions.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>

          {/* Product group */}
          <div className="space-y-1.5">
            <Label htmlFor="product_group">Product group</Label>
            <select
              id="product_group"
              className="w-full rounded-md border border-neutral-200 bg-white px-3 py-2 text-sm"
              disabled={!watchedPrgp}
              {...register("product_group")}
            >
              <option value="">— Select —</option>
              {itclOptions.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            {watchedPrgp && watchedItcl && (
              <p className="text-xs text-neutral-400">
                Commodity:{" "}
                {groups.find((g) => g.procurement_group === watchedPrgp && g.product_group === watchedItcl)
                  ?.commodity_codes.join(", ") ?? "—"}
              </p>
            )}
          </div>

          {/* Customer alias */}
          <div className="space-y-1.5">
            <Label htmlFor="customer_alias">
              Customer alias <Badge variant="outline" className="text-xs ml-1">optional</Badge>
            </Label>
            <Input
              id="customer_alias"
              placeholder="Customer part number"
              {...register("customer_alias")}
            />
          </div>

          {saveMutation.isError && (
            <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-600">
              Save failed. Please try again.
            </p>
          )}

          <div className="flex gap-3 justify-end pt-2">
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={isSubmitting || saveMutation.isPending || (!isDirty && !isNew)}>
              {saveMutation.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </form>
      </SheetContent>
    </Sheet>
  )
}
