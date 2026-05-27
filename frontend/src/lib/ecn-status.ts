import type { BadgeProps } from "@/components/ui/badge"

export const STATUS_LABELS: Record<number, string> = {
  0:  "Draft",
  30: "Eng Review",
  40: "Mgmt Review",
  25: "DC Approved",
  50: "Approved",
  60: "Implemented",
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
