import { useQuery } from "@tanstack/react-query"
import { Spinner } from "@/components/ui/spinner"
import { fetchAllBomChanges, type BOMChange } from "@/api/ecn"

/** Aggregate ECN-wide BOM Changes tab (Slice E, I2-6) — mirrors
 * RoutingTabContent.tsx exactly, for the "BOM lines added to existing ECN
 * detail/print output" scope item. */

const CHANGE_TYPE_BADGE: Record<string, string> = {
  ADD: "bg-emerald-100 text-emerald-700",
  CHANGE: "bg-blue-100 text-blue-700",
  DELETE: "bg-red-100 text-red-700",
}

interface Props {
  ecnId: string
  onManageItem: (itemId: string) => void
}

export default function BOMChangesTabContent({ ecnId, onManageItem }: Props) {
  const { data: changes = [], isLoading } = useQuery({
    queryKey: ["ecn-bom-changes-all", ecnId],
    queryFn: () => fetchAllBomChanges(ecnId),
  })

  if (isLoading) {
    return <div className="flex justify-center py-10"><Spinner size="sm" /></div>
  }

  if (changes.length === 0) {
    return (
      <div className="py-10 flex flex-col items-center gap-2">
        <p className="text-sm text-[#94a3b8]">No BOM changes defined yet.</p>
        <p className="text-xs text-[#cbd5e1]">Open an item and use its BOM Changes tab to add one.</p>
      </div>
    )
  }

  return (
    <div className="divide-y divide-neutral-100 rounded-lg border border-neutral-200 overflow-hidden">
      {changes.map((c: BOMChange) => (
        <div
          key={c.id}
          className="group flex items-start gap-3 px-4 py-3 bg-white hover:bg-neutral-50 transition-colors duration-100"
        >
          <span className="font-mono text-xs font-bold text-neutral-400 w-20 shrink-0 mt-0.5 truncate">
            {c.component_number}
          </span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-xs font-semibold text-[#0066cc]">{c.item_number}</span>
              <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${CHANGE_TYPE_BADGE[c.change_type] ?? "bg-neutral-100 text-neutral-600"}`}>
                {c.change_type}
              </span>
            </div>
            <p className="text-xs text-neutral-500 mt-0.5">
              {c.change_type !== "ADD" && (
                <>Old: {c.old_quantity ?? "—"} @ OPNO {c.old_operation_number ?? "—"}{" "}</>
              )}
              {c.change_type !== "DELETE" && (
                <>New: {c.quantity ?? "—"} {c.unit_of_measure ?? ""} @ OPNO {c.operation_number ?? "—"}</>
              )}
            </p>
          </div>
          <button
            type="button"
            className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0 text-xs font-medium text-[#0066cc] hover:underline"
            onClick={() => onManageItem(c.ecn_item_id)}
          >
            Manage
          </button>
        </div>
      ))}
    </div>
  )
}
