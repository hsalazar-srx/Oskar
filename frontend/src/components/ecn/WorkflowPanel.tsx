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

// ── StepBadge (private — only used in WorkflowPanel) ─────────────────────────

function StepBadge({ status, skipped }: { status: string; skipped: boolean }) {
  if (skipped) return <span className="text-xs text-neutral-400 italic">skipped</span>
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

  const panelActions = (ACTIONS_BY_STATUS[currentStatus] ?? []).filter(
    (a) => !HEADER_ACTION_TRIGGERS.has(a.trigger)
  )

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

          if ([65, 80, 90].includes(currentStatus) && !isActive && isFuture) return null

          const stageRa = stage.roleId ? roleMap[stage.roleId] : null

          return (
            <div key={stage.status} className="flex gap-3">
              {/* Dot + connector */}
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
              <div className="flex-1 pb-4 min-w-0">
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

                {/* Single-actor role row */}
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

                {/* Parallel approval steps (Management Review) */}
                {stage.parallel && (
                  <div className="mt-1.5 space-y-1">
                    {(ecn.approval_steps as ApprovalStep[] | undefined)?.length
                      ? (ecn.approval_steps as ApprovalStep[]).map((step) => (
                          <div
                            key={step.role_id}
                            className={`flex items-center justify-between rounded-md border px-3 py-2 ${
                              step.skipped             ? "border-neutral-100 bg-neutral-50 opacity-50" :
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

        {/* Terminal states */}
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
