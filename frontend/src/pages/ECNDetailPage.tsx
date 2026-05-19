import { useState } from "react"
import { useParams, useNavigate, Link } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { useAuthStore } from "@/store/auth"
import axiosInstance from "@/api/axios"
import ECNItemPanel from "@/components/ECNItemPanel"

// ── Status helpers ────────────────────────────────────────────────────────────

const STATUS_LABELS: Record<number, string> = {
  0: "Draft", 5: "Engineering Review", 10: "Management Review",
  20: "DC Review", 25: "DC Approved", 30: "Implemented",
  40: "Closed", 50: "On Hold", 60: "Rejected", 70: "Abandoned",
}

const STATUS_VARIANT: Record<number, "default" | "secondary" | "destructive" | "outline"> = {
  0: "outline", 5: "secondary", 10: "secondary", 20: "default",
  25: "default", 30: "default", 40: "outline", 50: "secondary",
  60: "destructive", 70: "destructive",
}

// Triggers available at each status, keyed by status code
// Each entry: { trigger, label, role, variant }
type ActionDef = { trigger: string; label: string; role?: string; variant?: "default" | "outline" | "destructive" }

const ACTIONS_BY_STATUS: Record<number, ActionDef[]> = {
  0: [
    { trigger: "submit", label: "Submit for Review", variant: "default" },
  ],
  5: [
    { trigger: "approve_engineering", label: "Approve", role: "SE", variant: "default" },
    { trigger: "reject", label: "Reject", role: "SE", variant: "destructive" },
    { trigger: "place_on_hold", label: "Hold", variant: "outline" },
  ],
  10: [
    { trigger: "approve_role", label: "Approve (my role)", variant: "default" },
    { trigger: "reject", label: "Reject", variant: "destructive" },
  ],
  20: [
    { trigger: "approve_role", label: "DC Approve", role: "DC", variant: "default" },
    { trigger: "reject", label: "Reject", role: "DC", variant: "destructive" },
  ],
  50: [
    { trigger: "resume", label: "Resume", variant: "default" },
    { trigger: "cancel", label: "Cancel", variant: "outline" },
  ],
  60: [
    { trigger: "resubmit", label: "Resubmit", variant: "default" },
  ],
}

// ── API helpers ───────────────────────────────────────────────────────────────

async function fetchECN(id: string) {
  const { data } = await axiosInstance.get(`/api/v1/ecn/${id}`)
  return data
}

async function fireTransition(
  ecnId: string,
  trigger: string,
  actorRole: string,
  updatedAt: string,
) {
  const { data } = await axiosInstance.patch(
    `/api/v1/ecn/${ecnId}/status`,
    { trigger, actor_role: actorRole },
    { headers: { "If-Unmodified-Since": updatedAt } },
  )
  return data
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ECNDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const user = useAuthStore((s) => s.user)

  const [selectedItemId, setSelectedItemId] = useState<string | null>(null)

  const { data: ecn, isLoading, isError } = useQuery({
    queryKey: ["ecn", id],
    queryFn: () => fetchECN(id!),
    enabled: !!id,
  })

  const transition = useMutation({
    mutationFn: ({ trigger, role }: { trigger: string; role: string }) =>
      fireTransition(id!, trigger, role, ecn?.updated_at),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ecn", id] })
      qc.invalidateQueries({ queryKey: ["ecns"] })
    },
  })

  if (isLoading) return <Loading />
  if (isError || !ecn) return <Error onBack={() => navigate("/ecn")} />

  const actions = ACTIONS_BY_STATUS[ecn.status] ?? []
  const userGroups = user?.groups ?? []

  // Derive a default role from user's groups for the action bar
  function defaultRole(action: ActionDef): string {
    if (action.role) return action.role
    const groupRole = userGroups.find((g: string) => g.startsWith("OSKAR-"))
    return groupRole?.replace("OSKAR-", "") ?? "OR"
  }

  return (
    <div className="min-h-screen bg-neutral-50">
      {/* Header */}
      <header className="border-b bg-white px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/ecn" className="text-sm text-neutral-400 hover:text-neutral-700">← ECN List</Link>
          <Separator orientation="vertical" className="h-4" />
          <span className="font-mono text-sm font-medium">{ecn.ecn_number}</span>
          <Badge variant={STATUS_VARIANT[ecn.status] ?? "outline"}>
            {STATUS_LABELS[ecn.status] ?? `Status ${ecn.status}`}
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          {actions.map((action) => (
            <Button
              key={action.trigger}
              size="sm"
              variant={action.variant ?? "outline"}
              disabled={transition.isPending}
              onClick={() => transition.mutate({ trigger: action.trigger, role: defaultRole(action) })}
            >
              {action.label}
            </Button>
          ))}
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-6 space-y-6">
        {transition.isError && (
          <div className="rounded bg-red-50 px-4 py-2 text-sm text-red-600">
            Transition failed — check your role or ECN state.
          </div>
        )}

        {/* ECN Header card */}
        <div className="rounded-lg border bg-white p-5 space-y-3">
          <h1 className="text-lg font-semibold">{ecn.title}</h1>
          <p className="text-sm text-neutral-600">{ecn.description}</p>
          <div className="flex flex-wrap gap-4 text-xs text-neutral-400 pt-1">
            <span>Originator: <span className="text-neutral-600">{ecn.originator_username}</span></span>
            <span>Facility: <span className="text-neutral-600">{ecn.facility}</span></span>
            <span>Revision: <span className="text-neutral-600">#{ecn.revision_number}</span></span>
            <span>Created: <span className="text-neutral-600">{new Date(ecn.created_at).toLocaleDateString()}</span></span>
          </div>
        </div>

        {/* Role assignments */}
        {ecn.role_assignments?.length > 0 && (
          <div className="rounded-lg border bg-white p-5">
            <h2 className="text-sm font-medium mb-3">Role assignments</h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {ecn.role_assignments.map((ra: { role_id: string; username: string }) => (
                <div key={ra.role_id} className="rounded border px-3 py-2 text-xs">
                  <span className="font-mono text-neutral-400">{ra.role_id}</span>
                  <span className="block text-neutral-700">{ra.username}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Items */}
        <div className="rounded-lg border bg-white p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-medium">Items</h2>
            <Button size="sm" variant="outline" onClick={() => setSelectedItemId("new")}>
              + Add item
            </Button>
          </div>
          {ecn.items?.length === 0 || !ecn.items ? (
            <p className="text-sm text-neutral-400">No items added yet.</p>
          ) : (
            <div className="divide-y">
              {ecn.items.map((item: { id: string; item_number: string; item_name: string; is_new_item: boolean }) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between py-2 cursor-pointer hover:bg-neutral-50 px-1 rounded"
                  onClick={() => setSelectedItemId(item.id)}
                >
                  <div>
                    <span className="font-mono text-sm">{item.item_number || "—"}</span>
                    <span className="ml-3 text-sm text-neutral-600">{item.item_name || "Untitled item"}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {item.is_new_item && <Badge variant="outline" className="text-xs">New</Badge>}
                    <span className="text-xs text-neutral-400">›</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>

      {/* Item panel (Sheet) */}
      {selectedItemId && (
        <ECNItemPanel
          ecnId={id!}
          itemId={selectedItemId === "new" ? null : selectedItemId}
          onClose={() => setSelectedItemId(null)}
        />
      )}
    </div>
  )
}

function Loading() {
  return (
    <div className="flex h-screen items-center justify-center text-sm text-neutral-400">
      Loading…
    </div>
  )
}

function Error({ onBack }: { onBack: () => void }) {
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-3 text-sm text-neutral-500">
      <p>ECN not found or failed to load.</p>
      <Button variant="outline" size="sm" onClick={onBack}>← Back to list</Button>
    </div>
  )
}
