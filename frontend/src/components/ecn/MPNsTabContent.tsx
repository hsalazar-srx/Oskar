import { useQuery } from "@tanstack/react-query"
import { Spinner } from "@/components/ui/spinner"
import { Badge } from "@/components/ui/badge"
import { fetchAllMPNs, type MPN } from "@/api/ecn"

interface Props {
  ecnId: string
  onManageItem: (itemId: string) => void
}

export default function MPNsTabContent({ ecnId, onManageItem }: Props) {
  const { data: mpns = [], isLoading } = useQuery({
    queryKey: ["ecn-mpns-all", ecnId],
    queryFn: () => fetchAllMPNs(ecnId),
  })

  if (isLoading) {
    return <div className="flex justify-center py-10"><Spinner size="sm" /></div>
  }

  if (mpns.length === 0) {
    return (
      <div className="py-10 flex flex-col items-center gap-2">
        <p className="text-sm text-[#94a3b8]">No MPNs added yet.</p>
        <p className="text-xs text-[#cbd5e1]">Open an item and use its MPNs tab to add one.</p>
      </div>
    )
  }

  return (
    <div className="divide-y divide-neutral-100 rounded-lg border border-neutral-200 overflow-hidden">
      {mpns.map((m: MPN) => (
        <div
          key={m.id}
          className="group flex items-start gap-3 px-4 py-3 bg-white hover:bg-neutral-50 transition-colors duration-100"
        >
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-xs font-semibold text-[#0066cc]">{m.item_number}</span>
              {m.is_default && <Badge variant="success" className="text-[10px]">Default</Badge>}
              {m.do_not_buy && <Badge variant="error" className="text-[10px]">Do not buy</Badge>}
            </div>
            <p className="text-sm text-neutral-700 mt-0.5 font-mono truncate">{m.mpn}</p>
            <p className="text-xs text-neutral-400 mt-0.5">
              {m.manufacturer ?? "—"}
              {m.lifecycle ? ` · ${m.lifecycle}` : ""}
              {m.lead_time_weeks != null ? ` · ${m.lead_time_weeks}w lead time` : ""}
            </p>
          </div>
          <button
            type="button"
            className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0 text-xs font-medium text-[#0066cc] hover:underline"
            onClick={() => onManageItem(m.ecn_item_id)}
          >
            Manage
          </button>
        </div>
      ))}
    </div>
  )
}
