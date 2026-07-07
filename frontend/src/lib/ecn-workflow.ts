// ECN domain constants, types, and pure utilities.
// No React imports — safe to import from any layer.

export type ActionDef = {
  trigger: string
  label: string
  role?: string
  variant?: "default" | "outline" | "destructive"
  needsConfirm?: boolean
  needsModal?: "reject" | "hold" | "cancel"
}

export const ACTIONS_BY_STATUS: Record<number, ActionDef[]> = {
  // DRAFT
  0:  [
        { trigger: "submit",              label: "Submit for Review",       role: "OR", variant: "default" },
        { trigger: "cancel",              label: "Cancel ECN",              role: "OR", variant: "destructive", needsModal: "cancel" },
      ],
  // ENGINEERING_REVIEW — actor_role resolved at runtime from the user's ECN role (SE or CE)
  30: [
        { trigger: "approve_engineering", label: "Approve — send to Management Review", role: "SE", variant: "default" },
        { trigger: "reject",              label: "Reject",                  role: "SE", variant: "destructive", needsModal: "reject" },
        { trigger: "place_on_hold",       label: "Place on Hold",           role: "DC", variant: "outline",     needsModal: "hold" },
        { trigger: "cancel",              label: "Cancel ECN",              role: "DC", variant: "destructive", needsModal: "cancel" },
      ],
  // MANAGEMENT_REVIEW — approve_role uses the user's pending step role_id
  40: [
        { trigger: "approve_role",        label: "Approve (my role)",       role: "QM", variant: "default" },
        { trigger: "reject",              label: "Reject",                  role: "QM", variant: "destructive", needsModal: "reject" },
        { trigger: "cancel",              label: "Cancel ECN",              role: "DC", variant: "destructive", needsModal: "cancel" },
      ],
  // DC_APPROVED
  25: [
        { trigger: "dc_approve",          label: "DC Approve — send to Movex", role: "DC", variant: "default" },
        { trigger: "reject",              label: "Reject",                  role: "DC", variant: "destructive", needsModal: "reject" },
        { trigger: "cancel",              label: "Cancel ECN",              role: "DC", variant: "destructive", needsModal: "cancel" },
      ],
  // APPROVED — DC manually triggers after Movex write is confirmed
  50: [
        { trigger: "movex_write_complete", label: "Mark Movex Write Complete", role: "DC", variant: "default" },
      ],
  // IMPLEMENTED — DC closes after implementation schedule is done
  60: [
        { trigger: "auto_close",          label: "Close ECN",               role: "DC", variant: "default" },
      ],
  // REJECTED
  65: [{ trigger: "resubmit",            label: "Resubmit",                role: "OR", variant: "default" }],
  // ON_HOLD
  90: [
        { trigger: "resume",              label: "Resume",                  role: "DC", variant: "default" },
        { trigger: "cancel",              label: "Cancel ECN",              role: "DC", variant: "destructive", needsModal: "cancel" },
      ],
}

export const ROLE_LABEL: Record<string, string> = {
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

export const TIMELINE_STAGES = [
  { status: 0,  label: "Draft",                    roleId: "OR", parallel: false },
  { status: 30, label: "Engineering Review",        roleId: "SE", parallel: false },
  { status: 40, label: "Management Review",         roleId: null, parallel: true  },
  { status: 25, label: "DC Approval",               roleId: "DC", parallel: false },
  { status: 50, label: "Approved — Movex Write",    roleId: null, parallel: false },
  { status: 60, label: "Implemented",               roleId: null, parallel: false },
  { status: 70, label: "Closed",                    roleId: null, parallel: false },
] as const

// Triggers that appear in the sticky header; others go in the workflow panel footer
export const HEADER_ACTION_TRIGGERS = new Set(["submit", "dc_approve", "movex_write_complete", "auto_close", "resubmit", "resume", "cancel"])

export const SCOPE_FLAGS: { key: string; label: string }[] = [
  { key: "is_new_item",                label: "New item" },
  { key: "new_parts",                  label: "New parts" },
  { key: "change_parts",               label: "Change parts" },
  { key: "bom_changes",                label: "BOM change" },
  { key: "routing_changes",            label: "Routing change" },
  { key: "operation_changes",          label: "Operation change" },
  { key: "lead_time_changes",          label: "Lead time change" },
  { key: "change_to_documents",        label: "Document change" },
  { key: "regulatory_impact",          label: "Regulatory impact" },
  { key: "requires_customer_approval", label: "Customer approval" },
]

export const TRIGGER_LABEL: Record<string, string> = {
  submit:                     "Engineering Review",
  approve_engineering:        "Management Review",
  approve_role:               "Management Review",
  complete_management_review: "DC Approved",
  dc_approve:                 "Approved — pending Movex write",
  movex_write_complete:       "Implemented",
  auto_close:                 "Closed",
  reject:                     "Rejected",
  resubmit:                   "Engineering Review",
  place_on_hold:              "On Hold",
  resume:                     "resumed",
  cancel:                     "Cancelled",
}

export function ageDays(createdAt: string): number {
  return Math.floor((Date.now() - new Date(createdAt).getTime()) / 86_400_000)
}
