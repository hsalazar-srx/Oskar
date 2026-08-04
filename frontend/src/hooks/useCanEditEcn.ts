import { useMemo } from "react"
import { useAuthStore } from "@/store/auth"
import {
  canEditEcnHeader,
  canEditItemsRoutingMpns,
  canEditNotes,
  canReassignRoles,
} from "@/lib/ecn-permissions"

export interface CanEditEcn {
  header: boolean
  itemsRoutingMpns: boolean
  notes: boolean
  roleReassignment: boolean
}

const DEFAULTS: CanEditEcn = {
  header: false,
  itemsRoutingMpns: false,
  notes: false,
  roleReassignment: false,
}

/**
 * Single source of truth for what the current user may edit on an ECN,
 * derived from ECN status + the current user's DC group membership /
 * originator relationship. Compute once per page and thread the result
 * down as props, rather than each panel recomputing its own ad hoc boolean.
 */
export function useCanEditEcn(
  ecn: { status: number; originator_username: string } | undefined,
): CanEditEcn {
  const user = useAuthStore((s) => s.user)

  return useMemo(() => {
    if (!ecn) return DEFAULTS

    const isUserDC = user?.groups?.includes("ecn-doc-controller") ?? false
    const isOriginator = user?.username === ecn.originator_username

    return {
      header: canEditEcnHeader(ecn.status, isUserDC, isOriginator),
      itemsRoutingMpns: canEditItemsRoutingMpns(ecn.status),
      notes: canEditNotes(ecn.status),
      roleReassignment: canReassignRoles(ecn.status),
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ecn?.status, ecn?.originator_username, user?.username, user?.groups])
}
