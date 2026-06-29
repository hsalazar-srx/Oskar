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
import ECNCommentsPanel from "@/components/ecn/ECNCommentsPanel"
import { ActionModal, ModalField } from "@/components/ecn/ActionModal"
import { ItemUploadDrawer } from "@/components/ecn/ItemUploadDrawer"

function transitionErrorMessage(err: unknown): string {
  const detail = (err as any)?.response?.data?.detail
  if (!detail) return "Transition failed — check your role assignment or ECN state."
  if (typeof detail === "string") return detail
  // 409 shape: { code, message, current_updated_at }
  if (typeof detail === "object" && detail.message) return detail.message
  return "Transition failed — check your role assignment or ECN state."
}

export default function ECNDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null)
  const [uploadDrawerOpen, setUploadDrawerOpen] = useState(false)
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
    select: (d: any[]) => d as Array<{
      id: string
      item_number: string
      item_name: string
      customer_alias: string | null
      is_new_item: boolean
    }>,
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
    onError: () => {
      // Refresh stale cache so the next attempt uses a fresh updated_at / status
      qc.invalidateQueries({ queryKey: ["ecn", id] })
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
    <div className="min-h-screen bg-[#f5f7fa] flex flex-col">
      {/* Sticky header */}
      <header className="sticky top-0 z-[1020] border-b border-[#e8ecf0] bg-white px-6 h-14 flex items-center justify-between shadow-[var(--shadow-xs)]">
        <div className="flex items-center gap-3 min-w-0">
          <Link to="/ecn" className="text-sm text-[#94a3b8] hover:text-[#475569] transition-colors duration-150 shrink-0">
            ← ECNs
          </Link>
          <span className="text-[#e2e8f0] shrink-0">|</span>
          <span className="font-mono text-sm font-bold text-[#0066cc] shrink-0">{ecn.ecn_number}</span>
          <Badge variant={statusBadgeVariant(ecn.status)} className="hidden sm:inline-flex shrink-0">
            {statusLabel(ecn.status)}
          </Badge>
          <span className="text-sm text-[#94a3b8] truncate hidden md:block">{ecn.title}</span>
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
          <div className="flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <svg className="w-4 h-4 shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clipRule="evenodd"/>
            </svg>
            <span>{transitionErrorMessage(transition.error)}</span>
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
          action={
            <div className="flex gap-2">
              {/* Upload button: visible always, disabled outside DRAFT */}
              {ecn.status === 0 ? (
                <Button size="sm" variant="outline" onClick={() => setUploadDrawerOpen(true)}>
                  ↑ Upload
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  disabled
                  title="Uploads only available in Draft status"
                  className="opacity-40 cursor-not-allowed"
                >
                  ↑ Upload
                </Button>
              )}
              <Button size="sm" variant="outline" onClick={() => setSelectedItemId("new")}>+ Add item</Button>
            </div>
          }
        >
          {items.length === 0 ? (
            <div className="py-10 flex flex-col items-center gap-2">
              <div className="w-10 h-10 rounded-full bg-[#f1f5f9] flex items-center justify-center">
                <svg className="w-5 h-5 text-[#94a3b8]" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25zM6.75 12h.008v.008H6.75V12zm0 3h.008v.008H6.75V15zm0 3h.008v.008H6.75V18z"/>
                </svg>
              </div>
              <p className="text-sm text-[#94a3b8]">No items added yet.</p>
              <p className="text-xs text-[#cbd5e1]">Items represent the parts or assemblies being changed.</p>
            </div>
          ) : (
            <>
              <div className="divide-y divide-[#f1f5f9]">
                {items.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className="w-full flex items-center justify-between py-3 px-1 rounded-lg hover:bg-[#f8fafc] text-left transition-colors duration-150 group"
                    onClick={() => setSelectedItemId(item.id)}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="font-mono text-sm font-semibold text-[#0066cc] shrink-0">
                        {item.item_number || <span className="text-[#cbd5e1] font-normal">—</span>}
                      </span>
                      <div className="flex flex-col min-w-0">
                        <span className="text-sm text-[#475569] truncate">{item.item_name || "Untitled item"}</span>
                        {item.customer_alias && (
                          <span className="text-[11px] font-mono text-[#94a3b8] truncate">Alias: {item.customer_alias}</span>
                        )}
                      </div>
                      {item.is_new_item && <Badge variant="info" className="shrink-0 text-[11px]">New</Badge>}
                    </div>
                    <svg className="w-4 h-4 text-[#cbd5e1] group-hover:text-[#94a3b8] transition-colors duration-150 shrink-0 ml-2" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5"/>
                    </svg>
                  </button>
                ))}
              </div>
              {/* Item count footer */}
              <div className="mt-3 pt-3 border-t border-[#f1f5f9] text-right">
                <span className="text-xs text-[#94a3b8]">
                  {items.length} item{items.length !== 1 ? "s" : ""} total
                </span>
              </div>
            </>
          )}
        </Section>
        <ECNCommentsPanel ecnId={id!} />
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

      <ItemUploadDrawer
        ecnId={id!}
        customerNumber={ecn?.customer_number ?? null}
        open={uploadDrawerOpen}
        onClose={() => setUploadDrawerOpen(false)}
        onSuccess={() => qc.invalidateQueries({ queryKey: ["ecn-items", id] })}
      />

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
        <div className="flex items-center gap-3 rounded-xl border border-emerald-200 bg-white px-4 py-3 shadow-[var(--shadow-lg)] text-sm">
          <div className="w-5 h-5 rounded-full bg-emerald-500 flex items-center justify-center shrink-0">
            <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5"/>
            </svg>
          </div>
          <span className="text-[#475569]">{toast?.from}</span>
          <svg className="w-3.5 h-3.5 text-[#94a3b8]" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3"/>
          </svg>
          <span className="text-[#0f172a] font-semibold">{toast?.to}</span>
          <button
            onClick={() => setToast(null)}
            className="ml-1 text-[#94a3b8] hover:text-[#475569] transition-colors duration-150 text-xs"
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
    <div className="rounded-xl border border-[#e8ecf0] bg-white shadow-[var(--shadow-sm)] overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-[#f1f5f9] bg-[#f8fafc]">
        <h2 className="text-sm font-semibold text-[#0f172a]">{title}</h2>
        {action}
      </div>
      <div className="p-5">{children}</div>
    </div>
  )
}

function Loading() {
  return (
    <div className="flex h-screen items-center justify-center bg-[#f5f7fa]">
      <Spinner size="lg" />
    </div>
  )
}

function ErrorState({ onBack }: { onBack: () => void }) {
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-3 bg-[#f5f7fa]">
      <div className="w-12 h-12 rounded-full bg-[#f1f5f9] flex items-center justify-center mb-1">
        <svg className="w-6 h-6 text-[#94a3b8]" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"/>
        </svg>
      </div>
      <p className="text-sm text-[#475569]">ECN not found or failed to load.</p>
      <Button variant="outline" size="sm" onClick={onBack}>← Back to list</Button>
    </div>
  )
}
