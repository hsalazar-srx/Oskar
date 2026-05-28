import { useState, useRef, useEffect, useCallback } from "react"
import { useParams, useNavigate, Link } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Spinner } from "@/components/ui/spinner"
import { useAuthStore } from "@/store/auth"
import axiosInstance from "@/api/axios"
import ECNItemPanel from "@/components/ECNItemPanel"
import { statusLabel, statusBadgeVariant } from "@/lib/ecn-status"

// ── Workflow action map (ADR-009) ─────────────────────────────────────────────

type ActionDef = {
  trigger: string
  label: string
  role?: string
  variant?: "default" | "outline" | "destructive"
  needsConfirm?: boolean
  needsModal?: "reject" | "hold"
}

const ACTIONS_BY_STATUS: Record<number, ActionDef[]> = {
  0:  [{ trigger: "submit",              label: "Submit for Review",  role: "OR", variant: "default" }],
  30: [
        { trigger: "approve_engineering", label: "Approve",           role: "SE", variant: "default" },
        { trigger: "reject",              label: "Reject",            role: "SE", variant: "destructive", needsModal: "reject" },
        { trigger: "place_on_hold",       label: "Place on Hold",     role: "DC", variant: "outline",     needsModal: "hold" },
      ],
  40: [
        { trigger: "approve_role",        label: "Approve (my role)", role: "QM", variant: "default" },
        { trigger: "reject",              label: "Reject",            role: "QM", variant: "destructive", needsModal: "reject" },
      ],
  25: [
        { trigger: "dc_approve",          label: "DC Approve",        role: "DC", variant: "default" },
        { trigger: "reject",              label: "Reject",            role: "DC", variant: "destructive", needsConfirm: true },
      ],
  65: [{ trigger: "resubmit",            label: "Resubmit",          role: "OR", variant: "default" }],
  90: [
        { trigger: "resume",             label: "Resume",             role: "OR", variant: "default" },
        { trigger: "cancel",             label: "Cancel",             role: "OR", variant: "outline", needsConfirm: true },
      ],
}

// ── API helpers ───────────────────────────────────────────────────────────────

async function fetchECN(id: string) {
  const { data } = await axiosInstance.get(`/api/v1/ecn/${id}`)
  return data
}

async function fetchItems(id: string) {
  const { data } = await axiosInstance.get(`/api/v1/ecn/${id}/items`)
  return data as { id: string; item_number: string; item_name: string; is_new_item: boolean }[]
}

async function fireTransition(
  ecnId: string,
  trigger: string,
  actorRole: string,
  updatedAt: string,
  extra?: Record<string, string>,
) {
  const { data } = await axiosInstance.patch(
    `/api/v1/ecn/${ecnId}/status`,
    { trigger, actor_role: actorRole, ...extra },
    { headers: { "If-Unmodified-Since": updatedAt } },
  )
  return data
}

async function assignRole(ecnId: string, roleId: string, username: string, actorRole: string) {
  const { data } = await axiosInstance.post(`/api/v1/ecn/${ecnId}/role-assignments`, {
    role_id: roleId,
    username,
    actor_role: actorRole,
  })
  return data
}

// ── Role + workflow metadata ──────────────────────────────────────────────────

const ROLE_LABEL: Record<string, string> = {
  OR: "Originator",
  DC: "Document Controller",
  SE: "Senior Engineer",
  CE: "Chief Engineer",
  EM: "Engineering Manager",
  QM: "Quality Manager",
  PM: "Production Manager",
  SC: "Supply Chain",
  FN: "Finance",
  CA: "Cost Accountant",
  AD: "Administrator",
}

// Ordered stages for the timeline — maps ECN status codes to stage definitions
const TIMELINE_STAGES = [
  { status: 0,    label: "Draft",              roleId: "OR", parallel: false },
  { status: 30,   label: "Engineering Review", roleId: "SE", parallel: false },
  { status: 40,   label: "Management Review",  roleId: null, parallel: true  },
  { status: 25,   label: "DC Approval",        roleId: "DC", parallel: false },
  { status: 50,   label: "Approved",           roleId: null, parallel: false },
  { status: 60,   label: "Implemented",        roleId: null, parallel: false },
  { status: 70,   label: "Closed",             roleId: null, parallel: false },
]

// Actions that belong in the header (non-contextual primary flow)
const HEADER_ACTION_TRIGGERS = new Set(["submit", "dc_approve", "resubmit", "resume", "cancel"])

// ── Helpers ───────────────────────────────────────────────────────────────────

const SCOPE_FLAGS: { key: string; label: string }[] = [
  { key: "is_new_item",              label: "New item" },
  { key: "routing_changes",          label: "Routing change" },
  { key: "operation_changes",        label: "Operation change" },
  { key: "new_parts",                label: "New parts" },
  { key: "lead_time_changes",        label: "Lead time change" },
  { key: "change_to_documents",      label: "Document change" },
  { key: "regulatory_impact",        label: "Regulatory impact" },
  { key: "requires_customer_approval", label: "Customer approval" },
]

function ageDays(createdAt: string) {
  return Math.floor((Date.now() - new Date(createdAt).getTime()) / 86_400_000)
}

const TRIGGER_LABEL: Record<string, string> = {
  submit:                 "Engineering Review",
  approve_engineering:    "Management Review",
  approve_role:           "Management Review",
  complete_management_review: "DC Approved",
  dc_approve:             "Approved",
  movex_write_complete:   "Implemented",
  auto_close:             "Closed",
  reject:                 "Rejected",
  resubmit:               "Engineering Review",
  place_on_hold:          "On Hold",
  resume:                 "resumed",
  cancel:                 "Cancelled",
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ECNDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null)
  const [toast, setToast] = useState<{ from: string; to: string } | null>(null)
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

  const [modal, setModal] = useState<{ action: ActionDef } | null>(null)

  const transition = useMutation({
    mutationFn: ({ trigger, role, extra }: { trigger: string; role: string; extra?: Record<string, string> }) =>
      fireTransition(id!, trigger, role, ecn?.updated_at, extra),
    onSuccess: (_, vars) => {
      const fromLabel = statusLabel(ecn?.status ?? 0)
      qc.invalidateQueries({ queryKey: ["ecn", id] })
      qc.invalidateQueries({ queryKey: ["ecn-items", id] })
      qc.invalidateQueries({ queryKey: ["ecns"] })
      const toLabel = TRIGGER_LABEL[vars.trigger] ?? "updated"
      showToast(fromLabel, toLabel)
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

  function defaultRole(action: ActionDef): string {
    return action.role ?? "OR"
  }

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

  const activeFlags = SCOPE_FLAGS.filter((f) => ecn[f.key])
  const age = ageDays(ecn.created_at)

  return (
    <div className="min-h-screen bg-neutral-50 flex flex-col">
      {/* Sticky header */}
      <header className="sticky top-0 z-[1020] border-b bg-white px-6 h-14 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3 min-w-0">
          <Link
            to="/ecn"
            className="text-sm text-neutral-400 hover:text-neutral-700 transition-colors duration-[150ms] shrink-0"
          >
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

        {/* ECN header card */}
        <div className="rounded-lg border bg-white p-5 shadow-sm hover:shadow-md transition-shadow duration-[200ms] space-y-4">
          <div>
            <h1 className="text-xl font-semibold text-neutral-900 leading-snug">{ecn.title}</h1>
            {ecn.description && (
              <p className="mt-2 text-sm text-neutral-600 leading-relaxed">{ecn.description}</p>
            )}
          </div>

          {/* Meta row */}
          <div className="flex flex-wrap gap-x-6 gap-y-1.5 pt-1 border-t border-neutral-100">
            <Meta label="Originator" value={ecn.originator_username} />
            <Meta label="Facility" value={ecn.facility} mono />
            <Meta label="Revision" value={`#${ecn.revision_number}`} mono />
            <Meta label="Created" value={new Date(ecn.created_at).toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric" })} />
            <Meta label="Age" value={`${age} day${age !== 1 ? "s" : ""}`} warn={age > 7} />
          </div>

          {/* Change scope flags */}
          {activeFlags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {activeFlags.map((f) => (
                <Badge key={f.key} variant="secondary">{f.label}</Badge>
              ))}
            </div>
          )}
        </div>

        {/* Workflow timeline */}
        <WorkflowPanel
          ecn={ecn}
          currentUsername={user?.username ?? ""}
          isUserDC={userGroups.includes("OSKAR-DC")}
          roleAssignIsPending={roleAssign.isPending}
          transitionIsPending={transition.isPending}
          onRoleAssign={(roleId, username) =>
            roleAssign.mutate({ roleId, username, actorRole: "DC" })
          }
          onApproveRole={(role) =>
            transition.mutate({ trigger: "approve_role", role })
          }
          onAction={(action) => handleAction(action)}
        />

        {/* Items */}
        <Section
          title={`Items (${items.length})`}
          action={
            <Button size="sm" variant="outline" onClick={() => setSelectedItemId("new")}>
              + Add item
            </Button>
          }
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
                    {item.is_new_item && (
                      <Badge variant="info" className="shrink-0">New</Badge>
                    )}
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
          onClose={() => setSelectedItemId(null)}
        />
      )}

      {/* Reject modal */}
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

      {/* Place on hold modal */}
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

// ── Sub-components ────────────────────────────────────────────────────────────

function Meta({ label, value, mono, warn }: { label: string; value: string; mono?: boolean; warn?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-neutral-400">{label}</span>
      <span className={`text-sm ${mono ? "font-mono" : ""} ${warn ? "text-orange-600 font-medium" : "text-neutral-700"}`}>
        {value}
      </span>
    </div>
  )
}

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

function StepBadge({ status, skipped }: { status: string; skipped: boolean }) {
  if (skipped) return <span className="text-xs text-neutral-400 italic">skipped</span>
  const variantMap: Record<string, "success" | "warning" | "error" | "neutral"> = {
    approved: "success",
    pending:  "warning",
    rejected: "error",
  }
  const variant = variantMap[status] ?? "neutral"
  return <Badge variant={variant}>{status}</Badge>
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

function RoleRow({ roleId, roleName, username, isAutoAssigned, canEdit, isSaving, onSave }: {
  roleId: string
  roleName?: string
  username: string | null
  isAutoAssigned?: boolean
  canEdit: boolean
  isSaving: boolean
  onSave: (username: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(username ?? "")
  const inputRef = useRef<HTMLInputElement>(null)

  function startEdit() {
    setValue(username ?? "")
    setEditing(true)
    setTimeout(() => inputRef.current?.focus(), 0)
  }

  function handleSave() {
    if (!value.trim()) return
    onSave(value.trim())
    setEditing(false)
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") handleSave()
    if (e.key === "Escape") setEditing(false)
  }

  return (
    <div className="flex items-center gap-2 rounded-md border border-neutral-100 bg-neutral-50 px-3 py-2 group">
      <div className="shrink-0 w-28">
        <span className="text-xs font-medium text-neutral-700 block leading-tight">
          {roleName ?? roleId}
        </span>
        <span className="font-mono text-[10px] text-neutral-400 leading-tight">{roleId}</span>
      </div>
      {editing ? (
        <div className="flex items-center gap-1 flex-1 min-w-0">
          <input
            ref={inputRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1 min-w-0 h-6 text-xs border border-neutral-300 rounded px-1.5 focus:outline-none focus:ring-1 focus:ring-neutral-900 bg-white"
            placeholder="username"
          />
          <button
            onClick={handleSave}
            disabled={isSaving || !value.trim()}
            className="text-xs text-neutral-600 hover:text-neutral-900 disabled:opacity-40 shrink-0"
          >
            {isSaving ? "…" : "✓"}
          </button>
          <button
            onClick={() => setEditing(false)}
            className="text-xs text-neutral-400 hover:text-neutral-700 shrink-0"
          >
            ✕
          </button>
        </div>
      ) : (
        <>
          <span className="text-xs text-neutral-600 truncate flex-1">
            {username ?? <em className="text-neutral-300">unassigned</em>}
            {isAutoAssigned && (
              <span className="ml-1.5 text-[10px] text-neutral-300" title="Auto-assigned from system roster">auto</span>
            )}
          </span>
          {canEdit && (
            <button
              onClick={startEdit}
              className="text-neutral-300 hover:text-neutral-600 opacity-0 group-hover:opacity-100 transition-opacity duration-[150ms] shrink-0 text-xs"
              title="Reassign role"
            >
              ✎
            </button>
          )}
        </>
      )}
    </div>
  )
}

// ── WorkflowPanel ────────────────────────────────────────────────────────────

type RoleAssignment = { role_id: string; username: string | null; is_auto_assigned: boolean }
type ApprovalStep   = { role_id: string; username: string | null; status: string; skipped: boolean }

function WorkflowPanel({
  ecn,
  currentUsername,
  isUserDC,
  roleAssignIsPending,
  transitionIsPending,
  onRoleAssign,
  onApproveRole,
  onAction,
}: {
  ecn: Record<string, unknown>
  currentUsername: string
  isUserDC: boolean
  roleAssignIsPending: boolean
  transitionIsPending: boolean
  onRoleAssign: (roleId: string, username: string) => void
  onApproveRole: (role: string) => void
  onAction: (action: ActionDef) => void
}) {
  const currentStatus = ecn.status as number
  const roleMap = Object.fromEntries(
    ((ecn.role_assignments ?? []) as RoleAssignment[]).map((r) => [r.role_id, r])
  )
  // Which step in the timeline are we at?
  const activeStageIdx = TIMELINE_STAGES.findIndex((s) => s.status === currentStatus)

  // Contextual panel-level actions (reject / hold) live here not in the header
  const panelActions = (ACTIONS_BY_STATUS[currentStatus] ?? []).filter(
    (a) => !HEADER_ACTION_TRIGGERS.has(a.trigger)
  )

  // Whether the current user has a pending approval step at MANAGEMENT_REVIEW
  const myPendingStep = currentStatus === 40
    ? (ecn.approval_steps as ApprovalStep[] | undefined)?.find(
        (s) => s.username === currentUsername && s.status === "pending" && !s.skipped
      )
    : undefined

  return (
    <div className="rounded-lg border bg-white shadow-sm hover:shadow-md transition-shadow duration-[200ms]">
      {/* Panel header */}
      <div className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-neutral-100">
        <div>
          <h2 className="text-sm font-semibold text-neutral-700">ECN Workflow</h2>
          <p className="text-xs text-neutral-400 mt-0.5">
            Who acts at each stage · DC may reassign roles
          </p>
        </div>
        {myPendingStep && (
          <Button
            size="sm"
            variant="default"
            disabled={transitionIsPending}
            onClick={() => onApproveRole(myPendingStep.role_id)}
            className="shrink-0"
          >
            Approve as {ROLE_LABEL[myPendingStep.role_id] ?? myPendingStep.role_id}
          </Button>
        )}
      </div>

      {/* Timeline */}
      <div className="px-5 py-4 space-y-0">
        {TIMELINE_STAGES.map((stage, idx) => {
          const isDone   = activeStageIdx > idx
          const isActive = activeStageIdx === idx
          const isFuture = activeStageIdx < idx

          // Terminal statuses break the happy path — show them separately
          if ([65, 80, 90].includes(currentStatus) && !isActive && isFuture) return null

          const stageRa = stage.roleId ? roleMap[stage.roleId] : null

          return (
            <div key={stage.status} className="flex gap-3">
              {/* Vertical connector + dot */}
              <div className="flex flex-col items-center shrink-0 w-6">
                <div className={`w-6 h-6 rounded-full border-2 flex items-center justify-center text-[10px] font-bold shrink-0 ${
                  isDone   ? "border-green-500 bg-green-500 text-white" :
                  isActive ? "border-neutral-900 bg-neutral-900 text-white" :
                             "border-neutral-200 bg-white text-neutral-300"
                }`}>
                  {isDone ? "✓" : isActive ? "▶" : ""}
                </div>
                {idx < TIMELINE_STAGES.length - 1 && (
                  <div className={`w-0.5 flex-1 min-h-[1.5rem] my-1 ${isDone ? "bg-green-300" : "bg-neutral-100"}`} />
                )}
              </div>

              {/* Stage content */}
              <div className={`flex-1 pb-4 min-w-0 ${idx < TIMELINE_STAGES.length - 1 ? "" : ""}`}>
                <div className="flex items-start justify-between gap-2 min-w-0">
                  <span className={`text-sm font-medium leading-6 ${
                    isActive ? "text-neutral-900" : isDone ? "text-neutral-500" : "text-neutral-300"
                  }`}>
                    {stage.label}
                  </span>
                  {isDone && (
                    <span className="text-xs text-green-600 font-medium shrink-0 mt-1">Done</span>
                  )}
                  {isActive && !stage.parallel && (
                    <span className="text-xs font-medium text-neutral-900 bg-neutral-100 px-2 py-0.5 rounded-full shrink-0">
                      In progress
                    </span>
                  )}
                </div>

                {/* Single-actor stage: role assignment row */}
                {stage.roleId && stageRa && (
                  <div className="mt-1.5">
                    <RoleRow
                      roleId={stage.roleId}
                      roleName={ROLE_LABEL[stage.roleId] ?? stage.roleId}
                      username={stageRa.username}
                      isAutoAssigned={stageRa.is_auto_assigned}
                      canEdit={isUserDC && stage.roleId !== "OR" && !isDone}
                      isSaving={roleAssignIsPending}
                      onSave={(u) => onRoleAssign(stage.roleId!, u)}
                    />
                  </div>
                )}

                {/* Parallel block: approval steps */}
                {stage.parallel && (
                  <div className="mt-1.5 space-y-1">
                    {(ecn.approval_steps as ApprovalStep[] | undefined)?.length
                      ? (ecn.approval_steps as ApprovalStep[]).map((step) => (
                          <div
                            key={step.role_id}
                            className={`flex items-center justify-between rounded-md border px-3 py-2 ${
                              step.skipped              ? "border-neutral-100 bg-neutral-50 opacity-50" :
                              step.status === "approved" ? "border-green-100 bg-green-50" :
                              step.status === "pending"  ? "border-amber-100 bg-amber-50" :
                              step.status === "rejected" ? "border-red-100 bg-red-50" :
                                                          "border-neutral-100 bg-neutral-50"
                            }`}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="font-mono text-xs text-neutral-400 w-7 shrink-0">{step.role_id}</span>
                              <span className="text-xs font-medium text-neutral-600 hidden sm:block">
                                {ROLE_LABEL[step.role_id] ?? step.role_id}
                              </span>
                              <span className="text-xs text-neutral-400 truncate">
                                {step.username ?? "—"}
                              </span>
                            </div>
                            <StepBadge status={step.status} skipped={step.skipped} />
                          </div>
                        ))
                      : isActive && (
                          <p className="text-xs text-neutral-400 italic">
                            Approval steps will appear here once the ECN enters Management Review.
                          </p>
                        )
                    }
                  </div>
                )}

              </div>
            </div>
          )
        })}

        {/* Special terminal states */}
        {currentStatus === 65 && (
          <div className="flex gap-3 items-start pt-1">
            <div className="w-6 h-6 rounded-full border-2 border-red-400 bg-red-400 flex items-center justify-center text-[10px] text-white font-bold shrink-0">✕</div>
            <div>
              <span className="text-sm font-medium text-red-700">Rejected</span>
              <p className="text-xs text-neutral-400 mt-0.5">Originator must resubmit or cancel.</p>
            </div>
          </div>
        )}
        {currentStatus === 80 && (
          <div className="flex gap-3 items-start pt-1">
            <div className="w-6 h-6 rounded-full border-2 border-neutral-300 bg-neutral-300 flex items-center justify-center text-[10px] text-white font-bold shrink-0">✕</div>
            <div><span className="text-sm font-medium text-neutral-500">Cancelled</span></div>
          </div>
        )}
        {currentStatus === 90 && (
          <div className="flex gap-3 items-start pt-1">
            <div className="w-6 h-6 rounded-full border-2 border-amber-400 bg-amber-400 flex items-center justify-center text-[10px] text-white font-bold shrink-0">⏸</div>
            <div>
              <span className="text-sm font-medium text-amber-700">On Hold</span>
              <p className="text-xs text-neutral-400 mt-0.5">DC may resume when ready.</p>
            </div>
          </div>
        )}
      </div>

      {/* Panel footer — contextual actions (Reject, Place on Hold) */}
      {panelActions.length > 0 && (
        <div className="flex items-center gap-2 px-5 py-3 border-t border-neutral-100 bg-neutral-50 rounded-b-lg">
          <span className="text-xs text-neutral-400 mr-1">Actions:</span>
          {panelActions.map((action) => (
            <Button
              key={action.trigger}
              size="sm"
              variant={action.variant ?? "outline"}
              disabled={transitionIsPending}
              onClick={() => onAction(action)}
            >
              {action.label}
            </Button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Modal helpers ────────────────────────────────────────────────────────────

function ModalField({
  name,
  label,
  type,
  multiline,
  placeholder,
  required,
}: {
  name: string
  label: string
  type?: "date"
  multiline?: boolean
  placeholder?: string
  required?: boolean
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={name} className="text-sm font-medium text-neutral-700">
        {label}{required && <span className="text-red-400 ml-0.5">*</span>}
      </label>
      {multiline ? (
        <textarea
          id={name}
          name={name}
          rows={3}
          required={required}
          placeholder={placeholder}
          className="w-full rounded-md border border-neutral-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900 resize-none"
        />
      ) : (
        <input
          id={name}
          name={name}
          type={type ?? "text"}
          required={required}
          placeholder={placeholder}
          className="w-full rounded-md border border-neutral-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900"
        />
      )}
    </div>
  )
}

function ActionModal({
  title,
  description,
  confirmLabel,
  confirmVariant = "default",
  onConfirm,
  onCancel,
  isPending,
  children,
}: {
  title: string
  description?: string
  confirmLabel: string
  confirmVariant?: "default" | "destructive"
  onConfirm: (data: Record<string, string>) => void
  onCancel: () => void
  isPending?: boolean
  children: React.ReactNode
}) {
  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    const data: Record<string, string> = {}
    fd.forEach((v, k) => { data[k] = v as string })
    onConfirm(data)
  }

  return (
    <div
      className="fixed inset-0 z-[1080] flex items-center justify-center bg-black/40"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel() }}
    >
      <div className="w-full max-w-md rounded-lg bg-white shadow-xl mx-4">
        <div className="px-5 pt-5 pb-2">
          <h3 className="text-base font-semibold text-neutral-900">{title}</h3>
          {description && <p className="text-sm text-neutral-500 mt-1">{description}</p>}
        </div>
        <form onSubmit={handleSubmit}>
          <div className="px-5 py-3 space-y-4">
            {children}
          </div>
          <div className="flex justify-end gap-2 px-5 py-4 border-t">
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 text-sm rounded-md border border-neutral-200 hover:bg-neutral-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isPending}
              className={`px-4 py-2 text-sm rounded-md font-medium transition-colors disabled:opacity-50 ${
                confirmVariant === "destructive"
                  ? "bg-red-600 text-white hover:bg-red-700"
                  : "bg-neutral-900 text-white hover:bg-neutral-800"
              }`}
            >
              {isPending ? "…" : confirmLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
