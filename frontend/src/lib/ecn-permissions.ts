import { ECNStatus } from "@/lib/ecn-status"

/**
 * Pure status/role predicates for what a user may edit on an ECN.
 * Consumed by useCanEditEcn (frontend/src/hooks/useCanEditEcn.ts) — kept as
 * standalone functions here so each predicate is independently testable and
 * so the different lock rules (DRAFT-only vs. locked-at-IMPLEMENTED) stay
 * visibly distinct rather than being collapsed into one "canEdit" boolean.
 */

/** Header/title/scope-flag fields: DRAFT or REJECTED, DC or originator only. */
export function canEditEcnHeader(status: number, isUserDC: boolean, isOriginator: boolean): boolean {
  return (status === ECNStatus.DRAFT || status === ECNStatus.REJECTED) && (isUserDC || isOriginator)
}

/** Items / Routing Ops / MPNs: DRAFT only, matching the backend's _require_draft guard. */
export function canEditItemsRoutingMpns(status: number): boolean {
  return status === ECNStatus.DRAFT
}

/** Notes/comments: editable at any status except once the ECN reaches IMPLEMENTED ("Movex Updated"). */
export function canEditNotes(status: number): boolean {
  return status !== ECNStatus.IMPLEMENTED
}

/** Role reassignment: locked once the ECN reaches IMPLEMENTED ("Movex Updated"). */
export function canReassignRoles(status: number): boolean {
  return status !== ECNStatus.IMPLEMENTED
}
