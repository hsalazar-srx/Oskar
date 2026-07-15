import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import axiosInstance from "@/api/axios"

interface HistoryEntry {
  id: string
  from_status: number | null
  from_status_name: string | null
  to_status: number
  to_status_name: string
  action: string
  actor_username: string
  actor_role: string | null
  notes: string | null
  sha256_self: string
  sha256_prev: string | null
  chain_valid: boolean
  created_at: string
}

async function fetchHistory(ecnId: string): Promise<HistoryEntry[]> {
  const { data } = await axiosInstance.get(`/api/v1/ecn/${ecnId}/history`)
  return data
}

const ACTION_LABEL: Record<string, string> = {
  create: "Created",
  submit: "Submitted for review",
  approve_engineering: "Engineering approved",
  approve_management: "Management approved",
  dc_approve: "DC approved",
  movex_write_complete: "Movex write complete",
  auto_close: "Auto-closed",
  reject: "Rejected",
  resubmit: "Resubmitted",
  cancel: "Cancelled",
  resume: "Resumed",
  hold: "Placed on hold",
}

function actionLabel(action: string): string {
  return ACTION_LABEL[action] ?? action
}

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString("en-AU", {
    day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  })
}

function shortHash(hash: string): string {
  return `${hash.slice(0, 8)}…${hash.slice(-6)}`
}

// ── RevisionLineagePanel ───────────────────────────────────────────────────────

interface Props {
  ecnId: string
}

export default function RevisionLineagePanel({ ecnId }: Props) {
  const [expanded, setExpanded] = useState(false)

  const { data: history = [], isLoading } = useQuery({
    queryKey: ["ecn-history", ecnId],
    queryFn: () => fetchHistory(ecnId),
    staleTime: 30_000,
  })

  const chainBroken = history.some((h) => !h.chain_valid)

  return (
    <div className="rounded-xl border border-[#e8ecf0] bg-white shadow-[var(--shadow-sm)] overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-[#f1f5f9] bg-[#f8fafc]">
        <div>
          <h2 className="text-sm font-semibold text-[#0f172a]">
            Revision Lineage
            {history.length > 0 && (
              <span className="ml-2 text-[11px] font-normal text-[#94a3b8]">{history.length} event{history.length !== 1 ? "s" : ""}</span>
            )}
          </h2>
          <p className="text-[11px] text-[#94a3b8] mt-0.5">
            Immutable audit chain — every status transition, SHA-256 linked.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {!isLoading && history.length > 0 && (
            chainBroken ? (
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-red-600 bg-red-50 border border-red-200 rounded-full px-2 py-0.5">
                Chain integrity issue
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2 py-0.5">
                Chain verified
              </span>
            )
          )}
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-[11px] font-semibold text-[#0066cc] hover:underline"
          >
            {expanded ? "Collapse" : "Expand"}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="p-5">
          {isLoading ? (
            <div className="flex justify-center py-4">
              <div className="w-4 h-4 border-2 border-[#0066cc]/20 border-t-[#0066cc] rounded-full animate-spin" />
            </div>
          ) : history.length === 0 ? (
            <p className="text-sm text-[#94a3b8] py-4 text-center">No transition history recorded yet.</p>
          ) : (
            <div className="relative pl-6">
              {/* Vertical timeline line */}
              <div className="absolute left-[7px] top-1 bottom-1 w-px bg-[#e2e8f0]" />

              <div className="space-y-5">
                {history.map((h) => (
                  <div key={h.id} className="relative">
                    <span
                      className={`absolute -left-6 top-0.5 w-3.5 h-3.5 rounded-full border-2 ${
                        h.chain_valid
                          ? "bg-white border-[#0066cc]"
                          : "bg-red-100 border-red-500"
                      }`}
                    />
                    <div className="flex items-baseline gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-[#0f172a]">{actionLabel(h.action)}</span>
                      {h.from_status_name && (
                        <span className="text-[11px] text-[#94a3b8] font-mono">
                          {h.from_status_name} → {h.to_status_name}
                        </span>
                      )}
                      {!h.from_status_name && (
                        <span className="text-[11px] text-[#94a3b8] font-mono">{h.to_status_name}</span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                      <span className="text-xs text-[#475569]">{h.actor_username}</span>
                      {h.actor_role && (
                        <span className="text-[10px] font-mono text-[#94a3b8] bg-[#f1f5f9] rounded px-1 py-0.5">{h.actor_role}</span>
                      )}
                      <span className="text-[11px] text-[#94a3b8]">{formatTimestamp(h.created_at)}</span>
                    </div>
                    {h.notes && (
                      <p className="mt-1 text-xs text-[#64748b] italic">{h.notes}</p>
                    )}
                    <p
                      className="mt-1 text-[10px] font-mono text-[#cbd5e1]"
                      title={h.sha256_self}
                    >
                      {shortHash(h.sha256_self)}
                      {!h.chain_valid && (
                        <span className="ml-1.5 text-red-500 font-sans">— expected prev hash mismatch</span>
                      )}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
