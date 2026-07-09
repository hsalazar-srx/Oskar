/**
 * ImplementationSchedulePanel — Mission Control view for ECN implementation checklist.
 *
 * Shows after status ≥ 60 (IMPLEMENTED). Designed to make a repetitive checklist feel
 * rewarding: animated progress ring, section cards with colour-coded rows, completion
 * celebration, and a "View Open Orders" drawer.
 */

import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import axiosInstance from "@/api/axios"

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  id: string
  section: number
  label: string
  applicable: boolean | null
  completed: boolean
  completed_by: string | null
  completed_at: string | null
  notes: string | null
}

interface OpenOrder {
  mo_number: string
  item_number: string
  quantity: number
  due_date: number  // YYYYMMDD
  facility: string
  status: string
}

interface Props {
  ecnId: string
  checklist: ChecklistItem[]

  isUserDC: boolean
  isOriginator: boolean
}

// ── API calls ─────────────────────────────────────────────────────────────────

async function patchChecklistItem(
  ecnId: string,
  itemId: string,
  patch: { applicable?: boolean | null; completed?: boolean; notes?: string },
) {
  const { data } = await axiosInstance.patch(`/api/v1/ecn/${ecnId}/checklist`, {
    item_id: itemId,
    ...patch,
  })
  return data
}

async function fetchOpenOrders(ecnId: string): Promise<OpenOrder[]> {
  const { data } = await axiosInstance.get(`/api/v1/ecn/${ecnId}/open-orders`)
  return data
}

// ── Progress ring ─────────────────────────────────────────────────────────────

function ProgressRing({ done, total }: { done: number; total: number }) {
  const r = 36
  const circ = 2 * Math.PI * r
  const pct = total === 0 ? 0 : done / total
  const dash = circ * pct
  const isComplete = done === total && total > 0

  return (
    <div className="relative flex items-center justify-center">
      <svg width="96" height="96" className="-rotate-90">
        {/* Track */}
        <circle cx="48" cy="48" r={r} fill="none" stroke="#e8ecf0" strokeWidth="8" />
        {/* Progress arc */}
        <circle
          cx="48" cy="48" r={r} fill="none"
          stroke={isComplete ? "#10b981" : "#0066cc"}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circ}`}
          style={{ transition: "stroke-dasharray 0.5s cubic-bezier(0.4, 0, 0.2, 1), stroke 0.3s" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        {isComplete ? (
          <svg className="w-7 h-7 text-emerald-500" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
          </svg>
        ) : (
          <>
            <span className="text-xl font-bold text-[#0f172a] leading-none">{done}</span>
            <span className="text-[10px] text-[#94a3b8] mt-0.5">/ {total}</span>
          </>
        )}
      </div>
    </div>
  )
}

// ── Applicable toggle ─────────────────────────────────────────────────────────

function ApplicableToggle({
  value,
  disabled,
  onChange,
}: {
  value: boolean | null
  disabled: boolean
  onChange: (v: boolean | null) => void
}) {
  const cycle = () => {
    if (disabled) return
    // null → true → false → null
    if (value === null) onChange(true)
    else if (value === true) onChange(false)
    else onChange(null)
  }

  const label = value === true ? "Applicable" : value === false ? "N/A" : "Decide"
  const cls =
    value === true
      ? "bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100"
      : value === false
      ? "bg-slate-100 text-[#94a3b8] border-[#e8ecf0] hover:bg-slate-200 line-through"
      : "bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100"

  return (
    <button
      type="button"
      onClick={cycle}
      disabled={disabled}
      title={disabled ? "Only the DC or originator can update this" : "Click to toggle: Applicable / N/A / Undecided"}
      className={`shrink-0 text-[11px] font-semibold px-2 py-0.5 rounded-full border transition-colors duration-150 ${cls} ${disabled ? "cursor-default opacity-60" : "cursor-pointer"}`}
    >
      {label}
    </button>
  )
}

// ── Notes textarea ────────────────────────────────────────────────────────────

function NotesField({
  value,
  disabled,
  onSave,
}: {
  value: string | null
  disabled: boolean
  onSave: (notes: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value ?? "")

  if (disabled && !value) return null

  if (!editing) {
    return (
      <button
        type="button"
        onClick={() => { if (!disabled) setEditing(true) }}
        disabled={disabled}
        className={`text-left text-[11px] ${value ? "text-[#475569]" : "text-[#cbd5e1]"} ${disabled ? "cursor-default" : "hover:text-[#0066cc] cursor-text"} transition-colors duration-150 w-full truncate`}
      >
        {value || (disabled ? "" : "Add note…")}
      </button>
    )
  }

  return (
    <div className="mt-1 w-full">
      <textarea
        autoFocus
        rows={2}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSave(draft); setEditing(false) }
          if (e.key === "Escape") setEditing(false)
        }}
        className="w-full text-xs px-2 py-1.5 rounded border border-[#d1d9e0] focus:border-[#0066cc] focus:outline-none focus:ring-1 focus:ring-[#0066cc]/20 resize-none text-[#475569]"
        placeholder="Add a note (Enter to save, Shift+Enter for newline)…"
      />
      <div className="flex gap-1.5 mt-1">
        <button
          type="button"
          onClick={() => { onSave(draft); setEditing(false) }}
          className="text-[11px] text-white bg-[#0066cc] hover:bg-[#0052a3] px-2 py-0.5 rounded transition-colors duration-150"
        >
          Save
        </button>
        <button
          type="button"
          onClick={() => { setDraft(value ?? ""); setEditing(false) }}
          className="text-[11px] text-[#94a3b8] hover:text-[#475569] px-1.5 py-0.5 rounded transition-colors duration-150"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// ── Checklist row ─────────────────────────────────────────────────────────────

function ChecklistRow({
  item,
  canEdit,
  isPending,
  onApplicable,
  onComplete,
  onNotes,
}: {
  item: ChecklistItem
  canEdit: boolean
  isPending: boolean
  onApplicable: (v: boolean | null) => void
  onComplete: () => void
  onNotes: (notes: string) => void
}) {
  const isNA = item.applicable === false
  const isDone = item.completed

  return (
    <div
      className={`flex items-start gap-3 py-3 px-4 rounded-lg transition-colors duration-200 ${
        isDone
          ? "bg-emerald-50/60"
          : isNA
          ? "bg-[#f8fafc] opacity-60"
          : "bg-white hover:bg-[#f8fafc]"
      }`}
    >
      {/* Complete button */}
      <button
        type="button"
        disabled={!canEdit || isNA || isPending}
        onClick={onComplete}
        title={
          isNA
            ? "Mark as applicable first"
            : isDone
            ? "Click to un-complete"
            : "Mark as done"
        }
        className={`mt-0.5 shrink-0 w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all duration-200 ${
          isDone
            ? "bg-emerald-500 border-emerald-500 text-white"
            : isNA
            ? "border-[#e8ecf0] bg-[#f1f5f9] cursor-not-allowed"
            : canEdit
            ? "border-[#d1d9e0] hover:border-[#0066cc] hover:bg-blue-50 cursor-pointer"
            : "border-[#e8ecf0] cursor-default"
        }`}
      >
        {isDone && (
          <svg className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth="3" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
          </svg>
        )}
      </button>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start gap-2 flex-wrap">
          <span
            className={`text-sm leading-snug ${
              isDone
                ? "text-[#94a3b8]"
                : isNA
                ? "text-[#cbd5e1]"
                : "text-[#0f172a]"
            }`}
          >
            {item.label}
          </span>
          <ApplicableToggle value={item.applicable} disabled={!canEdit || isPending} onChange={onApplicable} />
        </div>

        {/* Completion meta */}
        {isDone && item.completed_by && (
          <p className="text-[10px] text-emerald-600 mt-0.5">
            Completed by {item.completed_by}
            {item.completed_at && (
              <> · {new Date(item.completed_at).toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric" })}</>
            )}
          </p>
        )}

        {/* Notes */}
        <NotesField
          value={item.notes}
          disabled={!canEdit || isPending}
          onSave={onNotes}
        />
      </div>
    </div>
  )
}

// ── Open orders drawer ────────────────────────────────────────────────────────

function formatDate(yyyymmdd: number): string {
  const s = String(yyyymmdd)
  return `${s.slice(6)}/${s.slice(4, 6)}/${s.slice(0, 4)}`
}

function OpenOrdersDrawer({ ecnId, onClose }: { ecnId: string; onClose: () => void }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["ecn-open-orders", ecnId],
    queryFn: () => fetchOpenOrders(ecnId),
  })

  return (
    <div className="fixed inset-0 z-[1050] flex">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/20" onClick={onClose} />

      {/* Drawer panel */}
      <div className="absolute right-0 top-0 h-full w-full max-w-md bg-white shadow-[var(--shadow-lg)] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#e8ecf0]">
          <div>
            <h3 className="text-sm font-semibold text-[#0f172a]">Open Work Orders</h3>
            <p className="text-xs text-[#94a3b8] mt-0.5">Movex MOs linked to ECN items</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-[#94a3b8] hover:text-[#475569] transition-colors duration-150 p-1"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {isLoading && (
            <div className="flex items-center justify-center py-12">
              <div className="w-6 h-6 border-2 border-[#0066cc] border-t-transparent rounded-full animate-spin" />
            </div>
          )}
          {isError && (
            <p className="text-sm text-red-600 py-8 text-center">Failed to load open orders.</p>
          )}
          {data && data.length === 0 && (
            <div className="py-12 text-center">
              <div className="w-10 h-10 rounded-full bg-emerald-50 flex items-center justify-center mx-auto mb-3">
                <svg className="w-5 h-5 text-emerald-500" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                </svg>
              </div>
              <p className="text-sm font-medium text-[#0f172a]">No open work orders</p>
              <p className="text-xs text-[#94a3b8] mt-1">No active MOs found in Movex for this ECN's items.</p>
            </div>
          )}
          {data && data.length > 0 && (
            <div className="space-y-2">
              {data.map((o, i) => (
                <div key={i} className="rounded-lg border border-[#e8ecf0] p-3 bg-[#f8fafc]">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <span className="font-mono text-sm font-semibold text-[#0066cc]">{o.mo_number}</span>
                      <span className="text-xs text-[#94a3b8] ml-2">{o.item_number}</span>
                    </div>
                    <span className="text-[11px] font-mono text-[#475569] bg-white border border-[#e8ecf0] px-1.5 py-0.5 rounded">
                      Status {o.status}
                    </span>
                  </div>
                  <div className="mt-1.5 flex gap-4 text-[11px] text-[#94a3b8]">
                    <span>Qty: <strong className="text-[#475569]">{o.quantity}</strong></span>
                    <span>Due: <strong className="text-[#475569]">{formatDate(o.due_date)}</strong></span>
                    <span>Facility: <strong className="text-[#475569]">{o.facility}</strong></span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Main panel ────────────────────────────────────────────────────────────────

const SECTION_LABELS: Record<number, string> = {
  1: "Engineering",
  2: "Program Manager — WIP Impact",
}

export default function ImplementationSchedulePanel({
  ecnId,
  checklist,
  isUserDC,
  isOriginator,
}: Props) {
  const qc = useQueryClient()
  const [ordersOpen, setOrdersOpen] = useState(false)
  const canEdit = isUserDC || isOriginator

  const applicable = checklist.filter((i) => i.applicable !== false)
  const done = applicable.filter((i) => i.completed).length
  const total = applicable.filter((i) => i.applicable === true).length
  const undecided = checklist.filter((i) => i.applicable === null).length
  const isAllDone = total > 0 && done === total && undecided === 0

  const patch = useMutation({
    mutationFn: ({
      itemId,
      update,
    }: {
      itemId: string
      update: { applicable?: boolean | null; completed?: boolean; notes?: string }
    }) => patchChecklistItem(ecnId, itemId, update),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ecn", ecnId] }),
  })

  const sections = [1, 2] as const

  return (
    <div className="rounded-xl border border-[#e8ecf0] bg-white shadow-[var(--shadow-sm)] overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-[#f1f5f9] bg-[#f8fafc]">
        <div>
          <h2 className="text-sm font-semibold text-[#0f172a]">Implementation Schedule</h2>
          <p className="text-xs text-[#94a3b8] mt-0.5">
            {undecided > 0
              ? `${undecided} item${undecided !== 1 ? "s" : ""} need applicability decision`
              : total === 0
              ? "Mark items as applicable to begin"
              : isAllDone
              ? "All tasks complete — ready to close"
              : `${done} of ${total} applicable tasks complete`}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOrdersOpen(true)}
          className="flex items-center gap-1.5 text-xs text-[#0066cc] hover:text-[#0052a3] font-medium transition-colors duration-150 shrink-0"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25m18 0A2.25 2.25 0 0018.75 3H5.25A2.25 2.25 0 003 5.25m18 0H3"/>
          </svg>
          View Open Orders
        </button>
      </div>

      <div className="p-5 space-y-6">
        {/* Progress ring */}
        <div className="flex items-center gap-5">
          <ProgressRing done={done} total={total} />
          <div className="space-y-1">
            {isAllDone ? (
              <p className="text-sm font-semibold text-emerald-600">Implementation complete!</p>
            ) : (
              <p className="text-sm font-semibold text-[#0f172a]">
                {total === 0 ? "No tasks marked applicable yet" : `${done} / ${total} done`}
              </p>
            )}
            {undecided > 0 && (
              <p className="text-xs text-amber-600">
                {undecided} item{undecided !== 1 ? "s" : ""} need an applicability decision
              </p>
            )}
            {!canEdit && (
              <p className="text-xs text-[#94a3b8]">Read-only — only DC or originator can update</p>
            )}
          </div>
        </div>

        {/* Sections */}
        {sections.map((sec) => {
          const items = checklist.filter((i) => i.section === sec)
          const secDone = items.filter((i) => i.completed).length
          const secApplicable = items.filter((i) => i.applicable === true).length

          return (
            <div key={sec}>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-[#94a3b8]">
                  {SECTION_LABELS[sec]}
                </h3>
                {secApplicable > 0 && (
                  <span className={`text-[11px] font-medium ${secDone === secApplicable ? "text-emerald-600" : "text-[#94a3b8]"}`}>
                    {secDone}/{secApplicable}
                  </span>
                )}
              </div>
              <div className="rounded-lg border border-[#e8ecf0] divide-y divide-[#f1f5f9] overflow-hidden">
                {items.map((item) => (
                  <ChecklistRow
                    key={item.id}
                    item={item}
                    canEdit={canEdit}
                    isPending={patch.isPending}
                    onApplicable={(v) => patch.mutate({ itemId: item.id, update: { applicable: v } })}
                    onComplete={() =>
                      patch.mutate({
                        itemId: item.id,
                        update: { completed: !item.completed },
                      })
                    }
                    onNotes={(notes) => patch.mutate({ itemId: item.id, update: { notes } })}
                  />
                ))}
              </div>
            </div>
          )
        })}

        {/* Completion banner */}
        {isAllDone && (
          <div className="flex items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3">
            <div className="w-8 h-8 rounded-full bg-emerald-500 flex items-center justify-center shrink-0">
              <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
            </div>
            <div>
              <p className="text-sm font-semibold text-emerald-800">All implementation tasks complete</p>
              <p className="text-xs text-emerald-700">This ECN can now be closed.</p>
            </div>
          </div>
        )}
      </div>

      {ordersOpen && <OpenOrdersDrawer ecnId={ecnId} onClose={() => setOrdersOpen(false)} />}
    </div>
  )
}
