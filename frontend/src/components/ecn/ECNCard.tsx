import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ageDays, SCOPE_FLAGS } from "@/lib/ecn-workflow"

// ── Meta (private) ────────────────────────────────────────────────────────────

function Meta({ label, value, mono, warn }: { label: string; value: string; mono?: boolean; warn?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5 min-w-0">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-[#94a3b8]">{label}</span>
      <span className={`text-sm ${mono ? "font-mono" : "font-medium"} ${warn ? "text-amber-600" : "text-[#0f172a]"} truncate`}>
        {value}
      </span>
    </div>
  )
}

// ── Editable fields shape ──────────────────────────────────────────────────────

export interface ECNEditableFields {
  title: string
  description: string | null
  customer_ecn_refs: string | null
  is_new_item: boolean
  new_parts: boolean
  change_parts: boolean
  bom_changes: boolean
  routing_changes: boolean
  operation_changes: boolean
  lead_time_changes: boolean
  change_to_documents: boolean
  add_mpn: boolean
  regulatory_impact: boolean
  requires_customer_approval: boolean
}

function fieldsFromEcn(ecn: Record<string, unknown>): ECNEditableFields {
  return {
    title: (ecn.title as string) ?? "",
    description: (ecn.description as string | null) ?? null,
    customer_ecn_refs: (ecn.customer_ecn_refs as string | null) ?? null,
    is_new_item: Boolean(ecn.is_new_item),
    new_parts: Boolean(ecn.new_parts),
    change_parts: Boolean(ecn.change_parts),
    bom_changes: Boolean(ecn.bom_changes),
    routing_changes: Boolean(ecn.routing_changes),
    operation_changes: Boolean(ecn.operation_changes),
    lead_time_changes: Boolean(ecn.lead_time_changes),
    change_to_documents: Boolean(ecn.change_to_documents),
    add_mpn: Boolean(ecn.add_mpn),
    regulatory_impact: Boolean(ecn.regulatory_impact),
    requires_customer_approval: Boolean(ecn.requires_customer_approval),
  }
}

// ── ECNCard ───────────────────────────────────────────────────────────────────

interface Props {
  ecn: Record<string, unknown>
  canEditDmrUrl?: boolean
  onSaveDmrUrl?: (url: string | null) => void
  canEditDetails?: boolean
  onSaveDetails?: (fields: ECNEditableFields) => void
  savingDetails?: boolean
}

export default function ECNCard({
  ecn,
  canEditDmrUrl = false,
  onSaveDmrUrl,
  canEditDetails = false,
  onSaveDetails,
  savingDetails = false,
}: Props) {
  const activeFlags = SCOPE_FLAGS.filter((f) => ecn[f.key])
  const age = ageDays(ecn.created_at as string)

  const customerNumber = (ecn.customer_number as string | null) ?? null
  const customerName   = (ecn.customer_name as string | null) ?? null
  const customerDisplay = customerName
    ? `${customerName} (${customerNumber})`
    : (customerNumber ?? "—")

  const customerEcnRefs = (ecn.customer_ecn_refs as string | null) ?? null
  const refTags = customerEcnRefs
    ? customerEcnRefs.split(",").map((s) => s.trim()).filter(Boolean)
    : []

  const dmrUrl = (ecn.dmr_url as string | null) ?? null
  const [editingDmr, setEditingDmr] = useState(false)
  const [dmrInput, setDmrInput] = useState(dmrUrl ?? "")

  const [editingDetails, setEditingDetails] = useState(false)
  const [form, setForm] = useState<ECNEditableFields>(() => fieldsFromEcn(ecn))

  function handleDmrSave() {
    const trimmed = dmrInput.trim() || null
    onSaveDmrUrl?.(trimmed)
    setEditingDmr(false)
  }

  function startEditDetails() {
    setForm(fieldsFromEcn(ecn))
    setEditingDetails(true)
  }

  function handleDetailsSave() {
    if (!form.title.trim()) return
    onSaveDetails?.({
      ...form,
      title: form.title.trim(),
      description: form.description?.trim() || null,
      customer_ecn_refs: form.customer_ecn_refs?.trim() || null,
    })
    setEditingDetails(false)
  }

  return (
    <div className="rounded-xl border border-[#e8ecf0] bg-white shadow-[var(--shadow-sm)] overflow-hidden">
      {/* Blue top accent bar */}
      <div className="h-1 bg-[#0066cc]" />

      <div className="p-5 space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            {editingDetails ? (
              <div className="space-y-1.5">
                <input
                  type="text"
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  maxLength={200}
                  placeholder="ECN title"
                  autoFocus
                  className="w-full text-xl font-bold text-[#0f172a] border border-[#cbd5e1] rounded-md px-2.5 py-1 focus:outline-none focus:ring-2 focus:ring-[#0066cc]/30 focus:border-[#0066cc]"
                />
                <textarea
                  value={form.description ?? ""}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="Description (optional)"
                  rows={2}
                  className="w-full text-sm text-[#475569] border border-[#cbd5e1] rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-[#0066cc]/30 focus:border-[#0066cc] resize-y"
                />
              </div>
            ) : (
              <>
                <h1 className="text-xl font-bold text-[#0f172a] leading-snug">{ecn.title as string}</h1>
                {(ecn.description as string | null) && (
                  <p className="mt-1.5 text-sm text-[#475569] leading-relaxed">{ecn.description as string}</p>
                )}
              </>
            )}
          </div>

          {canEditDetails && !editingDetails && (
            <button
              type="button"
              onClick={startEditDetails}
              className="shrink-0 text-[11px] font-semibold text-[#0066cc] hover:underline px-1 py-0.5"
            >
              Edit
            </button>
          )}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 pt-3 border-t border-[#f1f5f9]">
          <Meta label="Originator" value={ecn.originator_username as string} />
          <Meta label="Facility"   value={ecn.facility as string} mono />
          <div className="flex flex-col gap-0.5 min-w-0">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-[#94a3b8]">Customer</span>
            <span className="text-sm font-medium text-[#0f172a] truncate" title={customerDisplay}>
              {customerDisplay}
            </span>
          </div>
          <Meta label="Revision"   value={`Rev ${ecn.revision_number}`} mono />
          <Meta
            label="Created"
            value={new Date(ecn.created_at as string).toLocaleDateString("en-AU", {
              day: "numeric", month: "short", year: "numeric",
            })}
          />
          <Meta label="Age" value={`${age} day${age !== 1 ? "s" : ""}`} warn={age > 7} />
        </div>

        {/* Customer ECN refs */}
        {editingDetails ? (
          <div className="flex flex-col gap-1 pt-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-[#94a3b8]">
              Customer ECN Refs <span className="normal-case font-normal text-[#cbd5e1]">(comma-separated)</span>
            </span>
            <input
              type="text"
              value={form.customer_ecn_refs ?? ""}
              onChange={(e) => setForm({ ...form, customer_ecn_refs: e.target.value })}
              placeholder="e.g. CUST-ECN-102, CUST-ECN-103"
              className="text-sm border border-[#cbd5e1] rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-[#0066cc]/30 focus:border-[#0066cc]"
            />
          </div>
        ) : refTags.length > 0 ? (
          <div className="flex flex-col gap-1 pt-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-[#94a3b8]">Customer ECN Refs</span>
            <div className="flex flex-wrap gap-1.5">
              {refTags.map((tag) => (
                <span key={tag} className="inline-block rounded-full border border-[#e2e8f0] bg-[#f8fafc] px-2.5 py-0.5 text-xs font-mono text-[#475569]">
                  {tag}
                </span>
              ))}
            </div>
          </div>
        ) : null}

        {/* DMR / SharePoint link */}
        <div className="flex flex-col gap-1 pt-1 border-t border-[#f1f5f9]">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-[#94a3b8]">DMR Document</span>
            {canEditDmrUrl && !editingDmr && (
              <button
                onClick={() => { setDmrInput(dmrUrl ?? ""); setEditingDmr(true) }}
                className="text-[11px] text-[#0066cc] hover:underline"
              >
                {dmrUrl ? "Edit" : "Add link"}
              </button>
            )}
          </div>

          {editingDmr ? (
            <div className="flex gap-2 items-center">
              <input
                type="url"
                value={dmrInput}
                onChange={(e) => setDmrInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleDmrSave(); if (e.key === "Escape") setEditingDmr(false) }}
                placeholder="https://srxglobal.sharepoint.com/..."
                autoFocus
                className="flex-1 text-sm border border-[#cbd5e1] rounded-md px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-[#0066cc]/30 focus:border-[#0066cc]"
              />
              <button onClick={handleDmrSave} className="text-xs font-medium text-white bg-[#0066cc] px-3 py-1.5 rounded-md hover:bg-[#0052a3]">Save</button>
              <button onClick={() => setEditingDmr(false)} className="text-xs text-[#64748b] hover:text-[#0f172a]">Cancel</button>
            </div>
          ) : dmrUrl ? (
            <a
              href={dmrUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-[#0066cc] hover:underline truncate"
              title={dmrUrl}
            >
              {dmrUrl}
            </a>
          ) : (
            <span className="text-sm text-[#94a3b8] italic">No document linked</span>
          )}
        </div>

        {/* Scope-change flags */}
        {editingDetails ? (
          <div className="flex flex-col gap-1.5 pt-1 border-t border-[#f1f5f9]">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-[#94a3b8]">Change Scope</span>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1.5">
              {SCOPE_FLAGS.map((f) => (
                <label key={f.key} className="flex items-center gap-1.5 text-sm text-[#334155] cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form[f.key as keyof ECNEditableFields] as boolean}
                    onChange={(e) => setForm({ ...form, [f.key]: e.target.checked })}
                    className="rounded border-[#cbd5e1] text-[#0066cc] focus:ring-[#0066cc]/30"
                  />
                  {f.label}
                </label>
              ))}
            </div>
          </div>
        ) : activeFlags.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {activeFlags.map((f) => (
              <Badge key={f.key} variant="secondary" className="text-[11px]">{f.label}</Badge>
            ))}
          </div>
        ) : null}

        {editingDetails && (
          <div className="flex justify-end gap-2 pt-2 border-t border-[#f1f5f9]">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setEditingDetails(false)}
              disabled={savingDetails}
            >
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={handleDetailsSave}
              disabled={savingDetails || !form.title.trim()}
            >
              {savingDetails ? "Saving…" : "Save changes"}
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
