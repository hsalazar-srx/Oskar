import { useNavigate } from "react-router-dom"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import axiosInstance from "@/api/axios"
import { fetchCustomers } from "@/api/ecn"

const SCOPE_OPTIONS = [
  { id: "new_parts",            label: "New parts",         desc: "Introducing parts not yet in Movex" },
  { id: "routing_changes",      label: "Routing change",    desc: "Add, update or remove routing steps" },
  { id: "operation_changes",    label: "Operation change",  desc: "Modify work centre or run time" },
  { id: "lead_time_changes",    label: "Lead time change",  desc: "Supplier lead time affected" },
  { id: "change_to_documents",  label: "Document change",   desc: "Drawing, spec or work instruction" },
  { id: "regulatory_impact",    label: "Regulatory impact", desc: "IPC, RoHS, REACH, customer standard" },
] as const

const schema = z.object({
  title: z.string().min(3, "At least 3 characters").max(200, "Max 200 characters"),
  description: z.string().min(10, "At least 10 characters"),
  facility: z.string().min(1),
  customer_number: z.string().min(2, "Select a customer").max(10),
  change_scope: z.array(z.string()).min(1, "Select at least one scope"),
})
type FormValues = z.infer<typeof schema>

async function createECN(body: FormValues) {
  const { data } = await axiosInstance.post("/api/v1/ecn/", body)
  return data
}

export default function ECNCreatePage() {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { facility: "D", change_scope: [] },
  })

  const { data: customers = [] } = useQuery({
    queryKey: ["customers"],
    queryFn: fetchCustomers,
  })

  const selectedScope = watch("change_scope") ?? []

  const toggleScope = (id: string) => {
    const current = selectedScope
    setValue(
      "change_scope",
      current.includes(id) ? current.filter((s) => s !== id) : [...current, id],
      { shouldValidate: true },
    )
  }

  const mutation = useMutation({
    mutationFn: createECN,
    onSuccess: (ecn) => {
      qc.invalidateQueries({ queryKey: ["ecns"] })
      navigate(`/ecn/${ecn.id}`, { replace: true })
    },
  })

  const onSubmit = (data: FormValues) => mutation.mutate(data)

  return (
    <div className="min-h-screen bg-neutral-50 flex flex-col">
      <header className="border-b bg-white px-6 h-14 flex items-center gap-3 shrink-0">
        <button
          onClick={() => navigate(-1)}
          className="text-sm text-neutral-400 hover:text-neutral-700 transition-colors"
        >
          ← ECNs
        </button>
        <span className="text-neutral-200">|</span>
        <span className="text-sm font-semibold text-neutral-800">New Engineering Change Notice</span>
      </header>

      <main className="flex-1 mx-auto w-full max-w-2xl px-6 py-8">
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">

          {/* Title */}
          <div className="rounded-lg border bg-white p-5 shadow-sm space-y-4">
            <h2 className="text-sm font-semibold text-neutral-700">Change details</h2>

            <div className="space-y-1.5">
              <Label htmlFor="title">Title <span className="text-red-400">*</span></Label>
              <Input
                id="title"
                placeholder="e.g. Replace C0402 caps on PCBA-LF-001 with Murata equivalent"
                className="h-10"
                {...register("title")}
              />
              {errors.title && <p className="text-xs text-red-500">{errors.title.message}</p>}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="description">Description <span className="text-red-400">*</span></Label>
              <Textarea
                id="description"
                rows={4}
                placeholder="Explain what is changing, why it's necessary, and any relevant part numbers or references."
                {...register("description")}
              />
              {errors.description && <p className="text-xs text-red-500">{errors.description.message}</p>}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="facility">Facility</Label>
              <select
                id="facility"
                className="h-10 w-full rounded-md border border-neutral-200 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900"
                {...register("facility")}
              >
                <option value="D">D — Melbourne</option>
                <option value="L">L — Johor Bahru</option>
              </select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="customer_number">Customer <span className="text-red-400">*</span></Label>
              <select
                id="customer_number"
                className="h-10 w-full rounded-md border border-neutral-200 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900"
                {...register("customer_number")}
                defaultValue=""
              >
                <option value="" disabled>— Select customer —</option>
                <option value="AC">AC — Generic / Common Stock</option>
                {customers.map((c) => (
                  <option key={c.cuno} value={c.cuno}>{c.cuno} — {c.name ?? "Unknown"}</option>
                ))}
              </select>
              {errors.customer_number && <p className="text-xs text-red-500">{errors.customer_number.message}</p>}
            </div>
          </div>

          {/* Change scope */}
          <div className="rounded-lg border bg-white p-5 shadow-sm space-y-3">
            <div>
              <h2 className="text-sm font-semibold text-neutral-700">Change scope <span className="text-red-400">*</span></h2>
              <p className="text-xs text-neutral-400 mt-0.5">Select all categories that apply to this change</p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {SCOPE_OPTIONS.map(({ id, label, desc }) => {
                const checked = selectedScope.includes(id)
                return (
                  <label
                    key={id}
                    className={`flex items-start gap-3 rounded-md border px-3 py-2.5 cursor-pointer transition-all ${
                      checked
                        ? "border-neutral-800 bg-neutral-900 text-white"
                        : "border-neutral-200 hover:border-neutral-300 hover:bg-neutral-50"
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="sr-only"
                      checked={checked}
                      onChange={() => toggleScope(id)}
                    />
                    <div className={`mt-0.5 w-4 h-4 rounded border shrink-0 flex items-center justify-center text-xs ${
                      checked ? "border-white bg-white text-neutral-900" : "border-neutral-300"
                    }`}>
                      {checked && "✓"}
                    </div>
                    <div className="min-w-0">
                      <span className="text-sm font-medium block">{label}</span>
                      <span className={`text-xs block mt-0.5 ${checked ? "text-neutral-300" : "text-neutral-400"}`}>{desc}</span>
                    </div>
                  </label>
                )
              })}
            </div>
            {errors.change_scope && (
              <p className="text-xs text-red-500">{errors.change_scope.message}</p>
            )}
          </div>

          {mutation.isError && (
            <div className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
              <span>⚠</span>
              <span>Failed to create ECN. Please try again.</span>
            </div>
          )}

          <div className="flex gap-3 justify-end">
            <Button type="button" variant="outline" onClick={() => navigate(-1)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting || mutation.isPending} className="min-w-28">
              {mutation.isPending ? "Creating…" : "Create ECN"}
            </Button>
          </div>
        </form>
      </main>
    </div>
  )
}
