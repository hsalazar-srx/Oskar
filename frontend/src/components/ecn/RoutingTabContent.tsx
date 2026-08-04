import { useQuery } from "@tanstack/react-query"
import { Spinner } from "@/components/ui/spinner"
import { fetchAllRoutingOps, type RoutingOp } from "@/api/ecn"

const CHANGE_TYPE_BADGE: Record<string, string> = {
  ADD: "bg-emerald-100 text-emerald-700",
  UPDATE: "bg-blue-100 text-blue-700",
  DELETE: "bg-red-100 text-red-700",
}

interface Props {
  ecnId: string
  onManageItem: (itemId: string) => void
}

export default function RoutingTabContent({ ecnId, onManageItem }: Props) {
  const { data: ops = [], isLoading } = useQuery({
    queryKey: ["ecn-routing-all", ecnId],
    queryFn: () => fetchAllRoutingOps(ecnId),
  })

  if (isLoading) {
    return <div className="flex justify-center py-10"><Spinner size="sm" /></div>
  }

  if (ops.length === 0) {
    return (
      <div className="py-10 flex flex-col items-center gap-2">
        <p className="text-sm text-[#94a3b8]">No routing operations defined yet.</p>
        <p className="text-xs text-[#cbd5e1]">Open an item and use its Routing Ops tab to add one.</p>
      </div>
    )
  }

  return (
    <div className="divide-y divide-neutral-100 rounded-lg border border-neutral-200 overflow-hidden">
      {ops.map((op: RoutingOp) => (
        <div
          key={op.id}
          className="group flex items-start gap-3 px-4 py-3 bg-white hover:bg-neutral-50 transition-colors duration-100"
        >
          <span className="font-mono text-xs font-bold text-neutral-400 w-8 shrink-0 mt-0.5">
            {String(op.operation_number).padStart(3, "0")}
          </span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-xs font-semibold text-[#0066cc]">{op.item_number}</span>
              <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${CHANGE_TYPE_BADGE[op.change_type] ?? "bg-neutral-100 text-neutral-600"}`}>
                {op.change_type}
              </span>
            </div>
            <p className="text-sm text-neutral-700 mt-0.5 truncate">{op.operation_description}</p>
            <p className="text-xs text-neutral-400 mt-0.5">
              {op.work_centre} · {op.run_time} min run
              {op.setup_time != null ? ` · ${op.setup_time} min setup` : ""}
            </p>
          </div>
          <button
            type="button"
            className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0 text-xs font-medium text-[#0066cc] hover:underline"
            onClick={() => onManageItem(op.ecn_item_id)}
          >
            Manage
          </button>
        </div>
      ))}
    </div>
  )
}
