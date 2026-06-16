import { useState, useRef, useEffect, useCallback } from "react"
import { useParams, useNavigate, Link } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Spinner } from "@/components/ui/spinner"
import { useAuthStore } from "@/store/auth"
import { fetchECN, fetchItems, fireTransition, assignRole } from "@/api/ecn"
import { statusLabel, statusBadgeVariant } from "@/lib/ecn-status"
import {
  ACTIONS_BY_STATUS, HEADER_ACTION_TRIGGERS, TRIGGER_LABEL, type ActionDef,
} from "@/lib/ecn-workflow"
import ECNCard from "@/components/ecn/ECNCard"
import WorkflowPanel from "@/components/ecn/WorkflowPanel"
import ECNItemPanel from "@/components/ECNItemPanel"
import { ActionModal, ModalField } from "@/components/ecn/ActionModal"

export default function ECNDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null)
  const [toast, setToast] = useState<{ from: string; to: string } | null>(null)
  const [modal, setModal] = useState<{ action: ActionDef } | null>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const showToast = useCallback((from: string, to: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current)
    setToast({ from, to })
    toastTimer.current = setTimeout(() => setToast(null), 5000)
  }, [])

  useEffect(() => () => { if (toastTimer.current) clearTimeout(toastTimer.current) }, [])

  const { data: ecn, isLoading, isError } = useQuery({
    queryKey: ["ecn", id],
    queryFn: () => fetchECN(id!),
    enabled: !!id,
  })

  const { data: items = [] } = useQuery({
    queryKey: ["ecn-items", id],
    queryFn: () => fetchItems(id!),
    enabled: !!id,
  })

  const transition = useMutation({
    mutationFn: ({ trigger, role, extra }: { trigger: string; role: string; extra?: Record<string, string> }) =>
      fireTransition(id!, trigger, role, ecn?.updated_at, extra),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["ecn", id] })
      qc.invalidateQueries({ queryKey: ["ecn-items", id] })
      qc.invalidateQueries({ queryKey: ["ecns"] })
      showToast(statusLabel(ecn?.status ?? 0), TRIGGER_LABEL[vars.trigger] ?? "updated")
    },
  })

  const roleAssign = useMutation({
    mutationFn: ({ roleId, username, actorRole }: { roleId: string; username: string; actorRole: string }) =>
      assignRole(id!, roleId, username, actorRole),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ecn", id] }),
  })

  if (isLoading) return <Loading />
  if (isError || !ecn) return <ErrorState onBack={() => navigate("/ecn")} />

  const actions = ACTIONS_BY_STATUS[ecn.status] ?? []
  const userGroups: string[] = user?.groups ?? []

  function defaultRole(action: ActionDef) { return action.role ?? "OR" }

  function handleAction(action: ActionDef) {
    if (action.needsModal) { setModal({ action }); return }
    if (action.needsConfirm && !window.confirm(`Confirm: ${action.label}?`)) return
    transition.mutate({ trigger: action.trigger, role: defaultRole(action) })
  }

  function fireModal(extra: Record<string, string>) {
    if (!modal) return
    transition.mutate({ trigger: modal.action.trigger, role: defaultRole(modal.action), extra })
    setModal(null)
  }

  return (
    <div className="min-h-screen bg-neutral-50 flex flex-col">
      {/* Sticky header */}
      <header className="sticky top-0 z-[1020] border-b bg-white px-6 h-14 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3 min-w-0">
          <Link to="/ecn" className="text-sm text-neutral-400 hover:text-neutral-700 transition-colors duration-[150ms] shrink-0">
            ← ECNs
          </Link>
          <span className="text-neutral-200 shrink-0">|</span>
          <span className="font-mono text-sm font-semibold text-neutral-800 shrink-0">{ecn.ecn_number}</span>
          <Badge variant={statusBadgeVariant(ecn.status)} className="hidden sm:inline-flex shrink-0">
            {statusLabel(ecn.status)}
          </Badge>
          <span className="text-sm text-neutral-500 truncate hidden md:block">{ecn.title}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-4">
          {transition.isPending && <Spinner size="sm" />}
          {actions.filter((a) => HEADER_ACTION_TRIGGERS.has(a.trigger)).map((action) => (
            <Button
              key={action.trigger}
              size="sm"
              variant={action.variant ?? "outline"}
              disabled={transition.isPending}
              onClick={() => handleAction(action)}
            >
              {action.label}
            </Button>
          ))}
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-4xl px-6 py-6 space-y-4">
        {transition.isError && (
          <div className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
            <span>⚠</span>
            <span>Transition failed — check your role assignment or ECN state.</span>
          </div>
        )}

        <ECNCard ecn={ecn} />

        <WorkflowPanel
          ecn={ecn}
          currentUsername={user?.username ?? ""}
          isUserDC={userGroups.includes("OSKAR-DC")}
          roleAssignIsPending={roleAssign.isPending}
          transitionIsPending={transition.isPending}
          onRoleAssign={(roleId, username) => roleAssign.mutate({ roleId, username, actorRole: "DC" })}
          onApproveRole={(role) => transition.mutate({ trigger: "approve_role", role })}
          onAction={handleAction}
        />

        <Section
          title={`Items (${items.length})`}
          action={<Button size="sm" variant="outline" onClick={() => setSelectedItemId("new")}>+ Add item</Button>}
        >
          {items.length === 0 ? (
            <div className="py-6 text-center">
              <p className="text-sm text-neutral-400">No items added yet.</p>
              <p className="text-xs text-neutral-300 mt-1">Items represent the parts or assemblies being changed.</p>
            </div>
          ) : (
            <div className="divide-y divide-neutral-100">
              {items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="w-full flex items-center justify-between py-2.5 px-1 rounded hover:bg-neutral-50 text-left transition-colors duration-[150ms] group"
                  onClick={() => setSelectedItemId(item.id)}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="font-mono text-sm text-neutral-700 shrink-0">
                      {item.item_number || <span className="text-neutral-300">No number</span>}
                    </span>
                    <span className="text-sm text-neutral-600 truncate">{item.item_name || "Untitled item"}</span>
                    {item.is_new_item && <Badge variant="info" className="shrink-0">New</Badge>}
                  </div>
                  <span className="text-neutral-300 group-hover:text-neutral-500 transition-colors duration-[150ms] shrink-0 ml-2">›</span>
                </button>
              ))}
            </div>
          )}
        </Section>
      </main>

      {selectedItemId && (
        <ECNItemPanel
          ecnId={id!}
          itemId={selectedItemId === "new" ? null : selectedItemId}
          nextLineNumber={items.length + 1}
          customerNumber={ecn?.customer_number ?? null}
          onClose={() => setSelectedItemId(null)}
        />
      )}

      {modal?.action.needsModal === "reject" && (
        <ActionModal
          title="Reject ECN"
          onCancel={() => setModal(null)}
          onConfirm={(values) => fireModal({ rejection_reason: values.reason })}
          isPending={transition.isPending}
          confirmLabel="Reject"
          confirmVariant="destructive"
        >
          <ModalField label="Rejection reason" name="reason" required placeholder="Describe why this ECN is being rejected…" multiline />
        </ActionModal>
      )}

      {modal?.action.needsModal === "hold" && (
        <ActionModal
          title="Place ECN on Hold"
          onCancel={() => setModal(null)}
          onConfirm={(values) => fireModal({ hold_reason: values.reason, expected_resume_date: values.date })}
          isPending={transition.isPending}
          confirmLabel="Place on Hold"
        >
          <ModalField label="Hold reason" name="reason" required placeholder="Describe why the ECN is being placed on hold…" multiline />
          <ModalField label="Expected resume date" name="date" required type="date" />
        </ActionModal>
      )}

      {/* Transition toast */}
      <div
        className={`fixed top-[72px] left-1/2 -translate-x-1/2 z-[1070] transition-all duration-300 ${
          toast ? "opacity-100 translate-y-0 pointer-events-auto" : "opacity-0 -translate-y-2 pointer-events-none"
        }`}
      >
        <div className="flex items-center gap-3 rounded-lg border border-green-200 bg-green-50 px-4 py-3 shadow-lg text-sm">
          <span className="text-green-600 text-base leading-none">✓</span>
          <span className="text-green-800 font-medium">Status changed</span>
          <span className="text-green-600">{toast?.from}</span>
          <span className="text-green-400">→</span>
          <span className="text-green-800 font-semibold">{toast?.to}</span>
          <button
            onClick={() => setToast(null)}
            className="ml-1 text-green-400 hover:text-green-700 transition-colors duration-[150ms] text-xs leading-none"
          >
            ✕
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Page-local helpers ────────────────────────────────────────────────────────

function Section({ title, children, action }: {
  title: string; children: React.ReactNode; action?: React.ReactNode
}) {
  return (
    <div className="rounded-lg border bg-white p-5 shadow-sm hover:shadow-md transition-shadow duration-[200ms]">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-neutral-700">{title}</h2>
        {action}
      </div>
      {children}
    </div>
  )
}

function Loading() {
  return (
    <div className="flex h-screen items-center justify-center">
      <Spinner size="lg" />
    </div>
  )
}

function ErrorState({ onBack }: { onBack: () => void }) {
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-3 text-sm text-neutral-500">
      <p>ECN not found or failed to load.</p>
      <Button variant="outline" size="sm" onClick={onBack}>← Back to list</Button>
    </div>
  )
}
