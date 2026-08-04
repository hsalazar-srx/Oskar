import type { BadgeProps } from "@/components/ui/badge"

/**
 * Mirrors src/workflow/machine.py's ECNStatus IntEnum. No codegen keeps these
 * in sync — update both places by hand when the backend enum changes.
 * (Plain object, not `enum` — this project's tsconfig has erasableSyntaxOnly.)
 */
export const ECNStatus = {
  DRAFT: 0,
  DC_APPROVED: 25,
  ENGINEERING_REVIEW: 30,
  MANAGEMENT_REVIEW: 40,
  APPROVED: 50,
  IMPLEMENTED: 60,
  REJECTED: 65,
  CLOSED: 70,
  CANCELLED: 80,
  ON_HOLD: 90,
} as const

export type ECNStatus = (typeof ECNStatus)[keyof typeof ECNStatus]

export const STATUS_LABELS: Record<number, string> = {
  0:  "Draft",
  30: "Eng Review",
  40: "Mgmt Review",
  25: "DC Approved",
  50: "Approved",
  60: "Movex Updated",
  65: "Rejected",
  70: "Closed",
  80: "Cancelled",
  90: "On Hold",
}

export const STATUS_BADGE_VARIANT: Record<number, BadgeProps["variant"]> = {
  0:  "neutral",
  30: "info",
  40: "purple",
  25: "warning",
  50: "success",
  60: "teal",
  65: "error",
  70: "neutral",
  80: "error",
  90: "orange",
}

export function statusLabel(s: number): string {
  return STATUS_LABELS[s] ?? `Status ${s}`
}

export function statusBadgeVariant(s: number): BadgeProps["variant"] {
  return STATUS_BADGE_VARIANT[s] ?? "neutral"
}

/** Retained for backward compat with any raw className usage */
export function statusColor(s: number): string {
  const map: Record<number, string> = {
    0:  "bg-neutral-100 text-neutral-600 border border-neutral-200",
    30: "bg-blue-50 text-blue-700 border border-blue-200",
    40: "bg-violet-50 text-violet-700 border border-violet-200",
    25: "bg-amber-50 text-amber-700 border border-amber-200",
    50: "bg-green-50 text-green-700 border border-green-200",
    60: "bg-teal-50 text-teal-700 border border-teal-200",
    65: "bg-red-50 text-red-700 border border-red-200",
    70: "bg-neutral-100 text-neutral-500 border border-neutral-200",
    80: "bg-red-50 text-red-500 border border-red-200",
    90: "bg-orange-50 text-orange-700 border border-orange-200",
  }
  return map[s] ?? "bg-neutral-100 text-neutral-600"
}
