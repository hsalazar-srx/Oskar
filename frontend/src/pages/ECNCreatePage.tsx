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
  { id: "new_parts",           label: "New parts",         desc: "Introducing parts not yet in Movex" },
  { id: "routing_changes",     label: "Routing change",    desc: "Add, update or remove routing steps" },
  { id: "operation_changes",   label: "Operation change",  desc: "Modify work centre or run time" },
  { id: "lead_time_changes",   label: "Lead time change",  desc: "Supplier lead time affected" },
  { id: "change_to_documents", label: "Document change",   desc: "Drawing, spec or work instruction" },
  { id: "regulatory_impact",   label: "Regulatory impact", desc: "IPC, RoHS, REACH, customer standard" },
] as const

const schema = z.object({
  title:           z.string().min(3, "At least 3 characters").max(200, "Max 200 characters"),
  description:     z.string().min(10, "At least 10 characters"),
  facility:        z.string().min(1),
  customer_number: z.string().min(2, "Select a customer").max(10),
  change_scope:    z.array(z.string()).min(1, "Select at least one scope"),
})
type FormValues = z.infer<typeof schema>

async function createECN(body: FormValues) {
  const { data } = await axiosInstance.post("/api/v1/ecn/", body)
  return data
}

const fieldClass = "h-10 w-full rounded-lg border border-[#d1d9e0] bg-white px-3 text-sm text-[#0f172a] placeholder:text-[#94a3b8] focus:outline-none focus:border-[#0066cc] focus:ring-2 focus:ring-[#0066cc]/20 transition-all duration-150"

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
    <div className="min-h-screen bg-[#f5f7fa] flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-[1020] border-b border-[#e8ecf0] bg-white shadow-[var(--shadow-xs)] px-6 h-14 flex items-center gap-3 shrink-0">
        <button
          onClick={() => navigate(-1)}
          className="text-sm text-[#94a3b8] hover:text-[#475569] transition-colors duration-150"
        >
          ← ECNs
        </button>
        <span className="text-[#d1d9e0]">|</span>
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded bg-[#eff6ff] flex items-center justify-center">
            <svg className="w-3 h-3 text-[#0066cc]" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4"/>
            </svg>
          </div>
          <span className="text-sm font-semibold text-[#0f172a]">New Engineering Change Notice</span>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-2xl px-6 py-8">
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">

          {/* Change details card */}
          <div className="rounded-xl border border-[#e8ecf0] bg-white shadow-[var(--shadow-sm)] overflow-hidden">
            <div className="px-5 py-4 border-b border-[#f1f5f9] bg-[#f8fafc]">
              <h2 className="text-sm font-semibold text-[#0f172a]">Change details</h2>
              <p className="text-xs text-[#94a3b8] mt-0.5">Describe what is changing and why</p>
            </div>

            <div className="p-5 space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="title" className="text-sm font-medium text-[#475569]">
                  Title <span className="text-red-400">*</span>
                </Label>
                <Input
                  id="title"
                  placeholder="e.g. Replace C0402 caps on PCBA-LF-001 with Murata equivalent"
                  className={fieldClass}
                  {...register("title")}
                />
                {errors.title && <p className="text-xs text-red-500">{errors.title.message}</p>}
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="description" className="text-sm font-medium text-[#475569]">
                  Description <span className="text-red-400">*</span>
                </Label>
                <Textarea
                  id="description"
                  rows={4}
                  placeholder="Explain what is changing, why it's necessary, and any relevant part numbers or references."
                  className="w-full rounded-lg border border-[#d1d9e0] bg-white px-3 py-2 text-sm text-[#0f172a] placeholder:text-[#94a3b8] focus:outline-none focus:border-[#0066cc] focus:ring-2 focus:ring-[#0066cc]/20 transition-all duration-150 resize-none"
                  {...register("description")}
                />
                {errors.description && <p className="text-xs text-red-500">{errors.description.message}</p>}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label htmlFor="facility" className="text-sm font-medium text-[#475569]">Facility</Label>
                  <select id="facility" className={fieldClass} {...register("facility")}>
                    <option value="D">D — Melbourne</option>
                    <option value="L">L — Johor Bahru</option>
                  </select>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="customer_number" className="text-sm font-medium text-[#475569]">
                    Customer <span className="text-red-400">*</span>
                  </Label>
                  <select
                    id="customer_number"
                    className={fieldClass}
                    {...register("customer_number")}
                    defaultValue=""
                  >
                    <option value="" disabled>— Select —</option>
                    <option value="AC">AC — Generic / Common Stock</option>
                    {customers.map((c) => (
                      <option key={c.cuno} value={c.cuno}>{c.cuno} — {c.name ?? "Unknown"}</option>
                    ))}
                  </select>
                  {errors.customer_number && <p className="text-xs text-red-500">{errors.customer_number.message}</p>}
                </div>
              </div>
            </div>
          </div>

          {/* Change scope card */}
          <div className="rounded-xl border border-[#e8ecf0] bg-white shadow-[var(--shadow-sm)] overflow-hidden">
            <div className="px-5 py-4 border-b border-[#f1f5f9] bg-[#f8fafc]">
              <h2 className="text-sm font-semibold text-[#0f172a]">
                Change scope <span className="text-red-400">*</span>
              </h2>
              <p className="text-xs text-[#94a3b8] mt-0.5">Select all categories that apply</p>
            </div>

            <div className="p-5">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {SCOPE_OPTIONS.map(({ id, label, desc }) => {
                  const checked = selectedScope.includes(id)
                  return (
                    <label
                      key={id}
                      className={`flex items-start gap-3 rounded-lg border px-3.5 py-3 cursor-pointer transition-all duration-150 ${
                        checked
                          ? "border-[#0066cc] bg-[#eff6ff] shadow-[0_0_0_1px_#0066cc]"
                          : "border-[#e8ecf0] hover:border-[#0066cc]/40 hover:bg-[#f8fafc]"
                      }`}
                    >
                      <input type="checkbox" className="sr-only" checked={checked} onChange={() => toggleScope(id)} />
                      <div className={`mt-0.5 w-4 h-4 rounded border-2 shrink-0 flex items-center justify-center ${
                        checked ? "border-[#0066cc] bg-[#0066cc]" : "border-[#d1d9e0]"
                      }`}>
                        {checked && (
                          <svg className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" strokeWidth="3" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5"/>
                          </svg>
                        )}
                      </div>
                      <div className="min-w-0">
                        <span className={`text-sm font-medium block ${checked ? "text-[#0066cc]" : "text-[#0f172a]"}`}>{label}</span>
                        <span className="text-xs block mt-0.5 text-[#94a3b8]">{desc}</span>
                      </div>
                    </label>
                  )
                })}
              </div>
              {errors.change_scope && (
                <p className="text-xs text-red-500 mt-3">{errors.change_scope.message}</p>
              )}
            </div>
          </div>

          {mutation.isError && (
            <div className="flex items-center gap-2.5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              <svg className="w-4 h-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clipRule="evenodd"/>
              </svg>
              Failed to create ECN — check all fields and try again.
            </div>
          )}

          <div className="flex gap-3 justify-end pt-1">
            <Button type="button" variant="outline" onClick={() => navigate(-1)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting || mutation.isPending} className="min-w-32">
              {mutation.isPending
                ? <span className="flex items-center gap-2"><span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin"/>Creating…</span>
                : "Create ECN"
              }
            </Button>
          </div>
        </form>
      </main>
    </div>
  )
}
