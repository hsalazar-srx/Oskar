import { useState, useRef, useEffect, useCallback } from "react"
import { useParams, useNavigate, Link } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Spinner } from "@/components/ui/spinner"
import { useAuthStore } from "@/store/auth"
import { fetchECN, fetchItems, fireTransition, assignRole, approveRole, updateEcn } from "@/api/ecn"
import { statusLabel, statusBadgeVariant, ECNStatus } from "@/lib/ecn-status"
import { useCanEditEcn } from "@/hooks/useCanEditEcn"
import {
  ACTIONS_BY_STATUS, HEADER_ACTION_TRIGGERS, TRIGGER_LABEL, type ActionDef,
} from "@/lib/ecn-workflow"
import ECNCard, { type ECNEditableFields } from "@/components/ecn/ECNCard"
import WorkflowPanel from "@/components/ecn/WorkflowPanel"
import ECNItemPanel from "@/components/ecn/ECNItemPanel"
import ECNEntityTabsSection from "@/components/ecn/ECNEntityTabsSection"
import ECNCommentsPanel from "@/components/ecn/ECNCommentsPanel"
import RevisionLineagePanel from "@/components/ecn/RevisionLineagePanel"
import ImplementationSchedulePanel from "@/components/ecn/ImplementationSchedulePanel"
import type { ChecklistItem } from "@/components/ecn/ImplementationSchedulePanel"
import { ActionModal, ModalField } from "@/components/ecn/ActionModal"

function transitionErrorMessage(err: unknown): string {
  const detail = (err as any)?.response?.data?.detail
  if (!detail) return "Transition failed — check your role assignment or ECN state."
  if (typeof detail === "string") return detail
  // 409 shapes: optimistic-lock { code, message, current_updated_at } OR
  // Slice E's BOM concurrency-gate conflict { message, diff }.
  if (typeof detail === "object" && detail.message) return detail.message
  return "Transition failed — check your role assignment or ECN state."
}

/** Slice E — extracts the BOM concurrency-gate's diff payload from a 409,
 * distinguishing it from the optimistic-lock 409 shape (which has no
 * `diff` key) so ECNItemPanel's conflict banner only ever shows for a real
 * BOM conflict, not a stale-write race on the ECN header. */
function transitionBomConflict(err: unknown): { message: string; diff: Record<string, unknown> } | null {
  const detail = (err as any)?.response?.data?.detail
  if (detail && typeof detail === "object" && detail.diff && typeof detail.diff === "object") {
    return { message: detail.message ?? "Live BOM has changed.", diff: detail.diff }
  }
  return null
}

export default function ECNDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null)
  const [selectedItemTab, setSelectedItemTab] = useState<"details" | "routing" | "bom" | "mpns">("details")
  const [toast, setToast] = useState<{ from: string; to: string } | null>(null)
  const [dismissedBomConflict, setDismissedBomConflict] = useState(false)
  const [modal, setModal] = useState<{ action: ActionDef } | null>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const showToast = useCallback((from: string, to: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current)
    setToast({ from, to })
    toastTimer.current = setTimeout(() => setToast(null), 5000)
  }, [])

  useEffect(() => () => { if (toastTimer.current) clearTimeout(toastTimer.current) }, [])

  const { data: ecn, isLoading, isFetching, isError } = useQuery({
    queryKey: ["ecn", id],
    queryFn: () => fetchECN(id!),
    enabled: !!id,
    staleTime: 0,
    refetchOnMount: "always",
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
    mutationFn: ({ trigger, role, extra }: { trigger: string; role: string; extra?: Record<string, string> }) => {
      // Always read updated_at from the live cache, not the render closure.
      // React Query may silently refetch in the background; the closure value can be
      // one version behind, causing a spurious 409 even when no real conflict exists.
      const liveEcn = qc.getQueryData<typeof ecn>(["ecn", id])
      return fireTransition(id!, trigger, role, liveEcn?.updated_at ?? ecn?.updated_at, extra)
    },
    onSuccess: (updated, vars) => {
      qc.setQueryData(["ecn", id], updated)        // write new ECN data immediately
      qc.invalidateQueries({ queryKey: ["ecn", id] })  // ensure refetch on next mount
      qc.invalidateQueries({ queryKey: ["ecn-items", id] })
      qc.invalidateQueries({ queryKey: ["ecns"], refetchType: "all" })
      showToast(statusLabel(ecn?.status ?? 0), TRIGGER_LABEL[vars.trigger] ?? "updated")
    },
    onError: () => {
      qc.invalidateQueries({ queryKey: ["ecn", id] })
    },
  })

  const roleAssign = useMutation({
    mutationFn: ({ roleId, username, actorRole }: { roleId: string; username: string; actorRole: string }) =>
      assignRole(id!, roleId, username, actorRole),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ecn", id] }),
  })

  const approveStep = useMutation({
    mutationFn: ({ role }: { role: string }) => approveRole(id!, role),
    onSuccess: (updated) => {
      qc.setQueryData(["ecn", id], updated)
      qc.invalidateQueries({ queryKey: ["ecns"], refetchType: "all" })
    },
  })

  const dmrUpdate = useMutation({
    mutationFn: (url: string | null) =>
      updateEcn(id!, { dmr_url: url }, ecn?.updated_at ?? ""),
    onSuccess: (updated) => {
      qc.setQueryData(["ecn", id], updated)
    },
  })

  const detailsUpdate = useMutation({
    mutationFn: (fields: ECNEditableFields) =>
      updateEcn(id!, fields, ecn?.updated_at ?? ""),
    onSuccess: (updated) => {
      qc.setQueryData(["ecn", id], updated)
      qc.invalidateQueries({ queryKey: ["ecns"], refetchType: "all" })
    },
  })

  const canEdit = useCanEditEcn(ecn)

  if (isLoading || isFetching) return <Loading />
  if (isError || !ecn) return <ErrorState onBack={() => navigate("/ecn")} />

  const actions = ACTIONS_BY_STATUS[ecn.status] ?? []
  const userGroups: string[] = user?.groups ?? []

  function defaultRole(action: ActionDef): string {
    // For approve_engineering the actor_role must be the user's actual role on this ECN
    // (SE or CE) — not the hardcoded default. Look up from role_assignments.
    if (action.trigger === "approve_engineering") {
      const assignments = (ecn.role_assignments ?? []) as Array<{ role_id: string; username: string }>
      const mine = assignments.find(
        (r) => r.username === user?.username && (r.role_id === "SE" || r.role_id === "CE")
      )
      if (mine) return mine.role_id
    }
    return action.role ?? "OR"
  }

  function handleAction(action: ActionDef) {
    if (action.needsModal) { setModal({ action }); return }
    if (action.needsConfirm && !window.confirm(`Confirm: ${action.label}?`)) return
    setDismissedBomConflict(false)
    transition.mutate({ trigger: action.trigger, role: defaultRole(action) })
  }

  function fireModal(extra: Record<string, string>) {
    if (!modal) return
    setDismissedBomConflict(false)
    transition.mutate({ trigger: modal.action.trigger, role: defaultRole(modal.action), extra })
    setModal(null)
  }

  function selectItem(itemId: string, tab: "details" | "routing" | "bom" | "mpns" = "details") {
    setSelectedItemTab(tab)
    setSelectedItemId(itemId)
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
        {(transition.isError || approveStep.isError) && (
          <div className="flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <svg className="w-4 h-4 shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clipRule="evenodd"/>
            </svg>
            <span>{transitionErrorMessage(transition.error ?? approveStep.error)}</span>
          </div>
        )}

        <ECNCard
          ecn={ecn}
          canEditDmrUrl={
            userGroups.includes("ecn-doc-controller") ||
            ecn.originator_username === user?.username
          }
          onSaveDmrUrl={(url) => dmrUpdate.mutate(url)}
          canEditDetails={canEdit.header}
          onSaveDetails={(fields) => detailsUpdate.mutate(fields)}
          savingDetails={detailsUpdate.isPending}
        />

        <WorkflowPanel
          ecn={ecn}
          currentUsername={user?.username ?? ""}
          isUserDC={userGroups.includes("ecn-doc-controller")}
          roleAssignIsPending={roleAssign.isPending}
          transitionIsPending={transition.isPending || approveStep.isPending}
          canReassignRoles={canEdit.roleReassignment}
          onRoleAssign={(roleId, username) => roleAssign.mutate({ roleId, username, actorRole: "DC" })}
          onApproveRole={(role) => approveStep.mutate({ role })}
          onAction={handleAction}
        />

        <ECNEntityTabsSection
          ecnId={id!}
          ecnNumber={ecn.ecn_number}
          customerNumber={ecn?.customer_number ?? null}
          items={items}
          canUpload={ecn.status === ECNStatus.DRAFT}
          canExport={ecn.status === ECNStatus.IMPLEMENTED}
          onSelectItem={selectItem}
          onAddItem={() => selectItem("new")}
          onItemsChanged={() => {
            qc.invalidateQueries({ queryKey: ["ecn-items", id] })
            qc.invalidateQueries({ predicate: (q) => q.queryKey[0] === "routing-ops" })
            qc.invalidateQueries({ predicate: (q) => q.queryKey[0] === "mpns" })
            qc.invalidateQueries({ predicate: (q) => q.queryKey[0] === "bom-changes" })
            qc.invalidateQueries({ predicate: (q) => q.queryKey[0] === "ecn-item" })
            qc.invalidateQueries({ queryKey: ["ecn-routing-all", id] })
            qc.invalidateQueries({ queryKey: ["ecn-mpns-all", id] })
            qc.invalidateQueries({ queryKey: ["ecn-bom-changes-all", id] })
          }}
        />
        <ECNCommentsPanel ecnId={id!} canEdit={canEdit.notes} />
        <RevisionLineagePanel ecnId={id!} />

        {ecn.status >= 60 && (
          <ImplementationSchedulePanel
            ecnId={id!}
            checklist={(ecn.extra_data?.impl_checklist ?? []) as ChecklistItem[]}
            isUserDC={userGroups.includes("ecn-doc-controller")}
            isOriginator={user?.username === ecn.originator_username}
          />
        )}
      </main>

      {selectedItemId && (
        <ECNItemPanel
          ecnId={id!}
          itemId={selectedItemId === "new" ? null : selectedItemId}
          nextLineNumber={items.length + 1}
          customerNumber={ecn?.customer_number ?? null}
          onClose={() => setSelectedItemId(null)}
          canEdit={canEdit.itemsRoutingMpns}
          initialTab={selectedItemTab}
          bomConflictDiff={!dismissedBomConflict ? transitionBomConflict(transition.error) : null}
          onDismissBomConflict={() => setDismissedBomConflict(true)}
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

      {modal?.action.needsModal === "cancel" && (
        <ActionModal
          title="Cancel ECN"
          description="This action is terminal. The ECN cannot be resubmitted once cancelled."
          onCancel={() => setModal(null)}
          onConfirm={(values) => fireModal({ notes: values.reason })}
          isPending={transition.isPending}
          confirmLabel="Cancel ECN"
          confirmVariant="destructive"
        >
          <ModalField label="Reason for cancellation" name="reason" required placeholder="Describe why this ECN is being cancelled…" multiline />
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
