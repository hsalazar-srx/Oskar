import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import type { BadgeProps } from "@/components/ui/badge"
import {
  ACTIONS_BY_STATUS,
  HEADER_ACTION_TRIGGERS,
  ROLE_LABEL,
  TIMELINE_STAGES,
  type ActionDef,
} from "@/lib/ecn-workflow"
import RoleRow from "@/components/ecn/RoleRow"

// ── Types ─────────────────────────────────────────────────────────────────────

type RoleAssignment = { role_id: string; username: string | null; is_auto_assigned: boolean }
type ApprovalStep   = { role_id: string; username: string | null; status: string; skipped: boolean }

// ── StepBadge ─────────────────────────────────────────────────────────────────

function StepBadge({ status, skipped }: { status: string; skipped: boolean }) {
  if (skipped) return <span className="text-xs text-[#94a3b8] italic">skipped</span>
  const variantMap: Record<string, BadgeProps["variant"]> = {
    approved: "success",
    pending:  "warning",
    rejected: "error",
  }
  return <Badge variant={variantMap[status] ?? "neutral"}>{status}</Badge>
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  ecn: Record<string, unknown>
  currentUsername: string
  isUserDC: boolean
  roleAssignIsPending: boolean
  transitionIsPending: boolean
  onRoleAssign: (roleId: string, username: string) => void
  onApproveRole: (role: string) => void
  onAction: (action: ActionDef) => void
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function WorkflowPanel({
  ecn,
  currentUsername,
  isUserDC,
  roleAssignIsPending,
  transitionIsPending,
  onRoleAssign,
  onApproveRole,
  onAction,
}: Props) {
  const currentStatus = ecn.status as number
  const roleMap = Object.fromEntries(
    ((ecn.role_assignments ?? []) as RoleAssignment[]).map((r) => [r.role_id, r])
  )
  const activeStageIdx = TIMELINE_STAGES.findIndex((s) => s.status === currentStatus)

  const myPendingStep = currentStatus === 40
    ? (ecn.approval_steps as ApprovalStep[] | undefined)?.find(
        (s) => s.username === currentUsername && s.status === "pending" && !s.skipped
      )
    : undefined

  const rawPanelActions = (ACTIONS_BY_STATUS[currentStatus] ?? []).filter(
    (a) => !HEADER_ACTION_TRIGGERS.has(a.trigger)
  )
  const panelActions = rawPanelActions.filter((a) => {
    if (a.trigger !== "approve_role") return true
    return !!myPendingStep
  })

  return (
    <div className="rounded-xl border border-[#e8ecf0] bg-white shadow-[var(--shadow-sm)] overflow-hidden">
      {/* Panel header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-[#f1f5f9] bg-[#f8fafc]">
        <div>
          <h2 className="text-sm font-semibold text-[#0f172a]">Workflow</h2>
          <p className="text-xs text-[#94a3b8] mt-0.5">DC may reassign roles at any stage</p>
        </div>
        {myPendingStep && (
          <Button
            size="sm"
            disabled={transitionIsPending}
            onClick={() => onApproveRole(myPendingStep.role_id)}
            className="shrink-0"
          >
            Approve as {ROLE_LABEL[myPendingStep.role_id] ?? myPendingStep.role_id}
          </Button>
        )}
      </div>

      {/* Timeline */}
      <div className="px-5 py-5">
        {TIMELINE_STAGES.map((stage, idx) => {
          const isDone   = activeStageIdx > idx
          const isActive = activeStageIdx === idx
          const isFuture = activeStageIdx < idx

          if ([65, 80, 90].includes(currentStatus) && !isActive && isFuture) return null

          const stageRa = stage.roleId ? roleMap[stage.roleId] : null
          const isLast  = idx === TIMELINE_STAGES.length - 1

          return (
            <div key={stage.status} className="flex gap-4">
              {/* Connector column */}
              <div className="flex flex-col items-center shrink-0 w-5">
                <div className={`w-5 h-5 rounded-full flex items-center justify-center shrink-0 ${
                  isDone   ? "bg-emerald-500 text-white" :
                  isActive ? "bg-[#0066cc] text-white ring-4 ring-[#0066cc]/15" :
                             "bg-[#f1f5f9] border-2 border-[#e2e8f0]"
                }`}>
                  {isDone && (
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5"/>
                    </svg>
                  )}
                  {isActive && (
                    <div className="w-2 h-2 rounded-full bg-white" />
                  )}
                </div>
                {!isLast && (
                  <div className={`w-0.5 flex-1 min-h-[1.75rem] my-1 rounded-full ${
                    isDone ? "bg-emerald-300" : "bg-[#e8ecf0]"
                  }`} />
                )}
              </div>

              {/* Stage content */}
              <div className="flex-1 pb-5 min-w-0">
                <div className="flex items-center justify-between gap-2 min-w-0 h-5 mb-2">
                  <span className={`text-sm font-semibold leading-5 ${
                    isActive ? "text-[#0f172a]" :
                    isDone   ? "text-[#94a3b8]" :
                               "text-[#cbd5e1]"
                  }`}>
                    {stage.label}
                  </span>
                  {isDone && (
                    <span className="text-[11px] font-semibold text-emerald-600 shrink-0">Done</span>
                  )}
                  {isActive && !stage.parallel && (
                    <span className="text-[11px] font-semibold text-[#0066cc] bg-[#eff6ff] px-2 py-0.5 rounded-full shrink-0">
                      In progress
                    </span>
                  )}
                </div>

                {/* Single-actor role row */}
                {stage.roleId && stageRa && (
                  <RoleRow
                    roleId={stage.roleId}
                    roleName={ROLE_LABEL[stage.roleId] ?? stage.roleId}
                    username={stageRa.username}
                    isAutoAssigned={stageRa.is_auto_assigned}
                    canEdit={isUserDC && stage.roleId !== "OR" && !isDone}
                    isSaving={roleAssignIsPending}
                    onSave={(u) => onRoleAssign(stage.roleId!, u)}
                  />
                )}

                {/* Parallel approval steps */}
                {stage.parallel && (
                  <div className="space-y-1.5">
                    {(ecn.approval_steps as ApprovalStep[] | undefined)?.length
                      ? (ecn.approval_steps as ApprovalStep[]).map((step) => (
                          <div
                            key={step.role_id}
                            className={`flex items-center justify-between rounded-lg border px-3 py-2 transition-colors ${
                              step.skipped               ? "border-[#f1f5f9] bg-[#f8fafc] opacity-50" :
                              step.status === "approved" ? "border-emerald-100 bg-emerald-50" :
                              step.status === "pending"  ? "border-amber-100 bg-amber-50" :
                              step.status === "rejected" ? "border-red-100 bg-red-50" :
                                                          "border-[#f1f5f9] bg-[#f8fafc]"
                            }`}
                          >
                            <div className="flex items-center gap-2.5 min-w-0">
                              <span className="font-mono text-[11px] font-bold text-[#94a3b8] w-7 shrink-0">{step.role_id}</span>
                              <span className="text-xs font-medium text-[#475569] hidden sm:block">
                                {ROLE_LABEL[step.role_id] ?? step.role_id}
                              </span>
                              <span className="text-xs text-[#94a3b8] truncate">
                                {step.username ?? "—"}
                              </span>
                            </div>
                            <StepBadge status={step.status} skipped={step.skipped} />
                          </div>
                        ))
                      : isActive && (
                          <p className="text-xs text-[#94a3b8] italic px-1">
                            Approval steps appear when the ECN enters Management Review.
                          </p>
                        )
                    }
                  </div>
                )}
              </div>
            </div>
          )
        })}

        {/* Terminal state indicators */}
        {currentStatus === 65 && (
          <div className="flex gap-4 items-start">
            <div className="w-5 h-5 rounded-full bg-red-500 flex items-center justify-center shrink-0">
              <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12"/>
              </svg>
            </div>
            <div>
              <span className="text-sm font-semibold text-red-700">Rejected</span>
              <p className="text-xs text-[#94a3b8] mt-0.5">Originator must resubmit or cancel.</p>
            </div>
          </div>
        )}
        {currentStatus === 80 && (
          <div className="flex gap-4 items-start">
            <div className="w-5 h-5 rounded-full bg-[#94a3b8] flex items-center justify-center shrink-0">
              <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12"/>
              </svg>
            </div>
            <span className="text-sm font-semibold text-[#94a3b8]">Cancelled</span>
          </div>
        )}
        {currentStatus === 90 && (
          <div className="flex gap-4 items-start">
            <div className="w-5 h-5 rounded-full bg-amber-500 flex items-center justify-center shrink-0">
              <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM7 8a1 1 0 012 0v4a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v4a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd"/>
              </svg>
            </div>
            <div>
              <span className="text-sm font-semibold text-amber-700">On Hold</span>
              <p className="text-xs text-[#94a3b8] mt-0.5">DC may resume when ready.</p>
            </div>
          </div>
        )}
      </div>

      {/* Footer actions (Reject, Place on Hold) */}
      {panelActions.length > 0 && (
        <div className="flex items-center gap-2 px-5 py-3 border-t border-[#f1f5f9] bg-[#f8fafc]">
          <span className="text-xs text-[#94a3b8] mr-1">Actions</span>
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
