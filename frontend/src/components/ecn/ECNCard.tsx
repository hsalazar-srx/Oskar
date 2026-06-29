import { Badge } from "@/components/ui/badge"
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

// ── ECNCard ───────────────────────────────────────────────────────────────────

interface Props {
  ecn: Record<string, unknown>
}

export default function ECNCard({ ecn }: Props) {
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

  return (
    <div className="rounded-xl border border-[#e8ecf0] bg-white shadow-[var(--shadow-sm)] overflow-hidden">
      {/* Blue top accent bar */}
      <div className="h-1 bg-[#0066cc]" />

      <div className="p-5 space-y-4">
        <div>
          <h1 className="text-xl font-bold text-[#0f172a] leading-snug">{ecn.title as string}</h1>
          {(ecn.description as string | null) && (
            <p className="mt-1.5 text-sm text-[#475569] leading-relaxed">{ecn.description as string}</p>
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
        {refTags.length > 0 && (
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
        )}

        {activeFlags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {activeFlags.map((f) => (
              <Badge key={f.key} variant="secondary" className="text-[11px]">{f.label}</Badge>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
