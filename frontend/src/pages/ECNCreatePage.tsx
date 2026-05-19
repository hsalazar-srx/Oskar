import { useNavigate } from "react-router-dom"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import axiosInstance from "@/api/axios"

const SCOPE_OPTIONS = [
  { id: "bom", label: "BOM change" },
  { id: "routing_changes", label: "Routing change" },
  { id: "operation_changes", label: "Operation change" },
  { id: "new_parts", label: "New parts" },
  { id: "lead_time_changes", label: "Lead time change" },
  { id: "change_to_documents", label: "Document change" },
  { id: "regulatory_impact", label: "Regulatory impact" },
] as const

const schema = z.object({
  title: z.string().min(3, "Title must be at least 3 characters").max(200),
  description: z.string().min(10, "Description must be at least 10 characters"),
  facility: z.string().min(1),
  change_scope: z.array(z.string()).min(1, "Select at least one change scope"),
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
    defaultValues: { facility: "L", change_scope: [] },
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
    <div className="min-h-screen bg-neutral-50">
      <header className="border-b bg-white px-6 py-3 flex items-center gap-3">
        <button
          onClick={() => navigate(-1)}
          className="text-sm text-neutral-400 hover:text-neutral-700"
        >
          ← Back
        </button>
        <span className="font-semibold">New ECN</span>
      </header>

      <main className="mx-auto max-w-2xl px-6 py-8">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Engineering Change Notice</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
              <div className="space-y-1.5">
                <Label htmlFor="title">Title</Label>
                <Input id="title" placeholder="Short description of the change" {...register("title")} />
                {errors.title && <p className="text-xs text-red-500">{errors.title.message}</p>}
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  rows={4}
                  placeholder="Detailed description of what is changing and why"
                  {...register("description")}
                />
                {errors.description && <p className="text-xs text-red-500">{errors.description.message}</p>}
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="facility">Facility</Label>
                <select
                  id="facility"
                  className="w-full rounded-md border border-neutral-200 bg-white px-3 py-2 text-sm"
                  {...register("facility")}
                >
                  <option value="L">L — Melbourne</option>
                </select>
              </div>

              <div className="space-y-2">
                <Label>Change scope <span className="text-neutral-400 font-normal">(select all that apply)</span></Label>
                <div className="grid grid-cols-2 gap-2">
                  {SCOPE_OPTIONS.map(({ id, label }) => (
                    <label
                      key={id}
                      className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm cursor-pointer transition-colors ${
                        selectedScope.includes(id)
                          ? "border-neutral-800 bg-neutral-800 text-white"
                          : "border-neutral-200 hover:bg-neutral-50"
                      }`}
                    >
                      <input
                        type="checkbox"
                        className="sr-only"
                        checked={selectedScope.includes(id)}
                        onChange={() => toggleScope(id)}
                      />
                      {label}
                    </label>
                  ))}
                </div>
                {errors.change_scope && (
                  <p className="text-xs text-red-500">{errors.change_scope.message}</p>
                )}
              </div>

              {mutation.isError && (
                <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-600">
                  Failed to create ECN. Please try again.
                </p>
              )}

              <div className="flex gap-3 justify-end pt-2">
                <Button type="button" variant="outline" onClick={() => navigate(-1)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isSubmitting || mutation.isPending}>
                  {mutation.isPending ? "Creating…" : "Create ECN"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </main>
    </div>
  )
}
