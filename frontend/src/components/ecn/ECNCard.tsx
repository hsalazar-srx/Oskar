import { Badge } from "@/components/ui/badge"
import { ageDays, SCOPE_FLAGS } from "@/lib/ecn-workflow"

// ── Meta (private — only used in ECNCard) ────────────────────────────────────

function Meta({ label, value, mono, warn }: { label: string; value: string; mono?: boolean; warn?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-neutral-400">{label}</span>
      <span className={`text-sm ${mono ? "font-mono" : ""} ${warn ? "text-orange-600 font-medium" : "text-neutral-700"}`}>
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

  return (
    <div className="rounded-lg border bg-white p-5 shadow-sm hover:shadow-md transition-shadow duration-[200ms] space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-neutral-900 leading-snug">{ecn.title as string}</h1>
        {(ecn.description as string | null) && (
          <p className="mt-2 text-sm text-neutral-600 leading-relaxed">{ecn.description as string}</p>
        )}
      </div>

      <div className="flex flex-wrap gap-x-6 gap-y-1.5 pt-1 border-t border-neutral-100">
        <Meta label="Originator" value={ecn.originator_username as string} />
        <Meta label="Facility" value={ecn.facility as string} mono />
        <Meta label="Customer" value={(ecn.customer_number as string | null) ?? "—"} mono />
        <Meta label="Revision" value={`#${ecn.revision_number}`} mono />
        <Meta
          label="Created"
          value={new Date(ecn.created_at as string).toLocaleDateString("en-AU", {
            day: "numeric", month: "short", year: "numeric",
          })}
        />
        <Meta label="Age" value={`${age} day${age !== 1 ? "s" : ""}`} warn={age > 7} />
      </div>

      {activeFlags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {activeFlags.map((f) => (
            <Badge key={f.key} variant="secondary">{f.label}</Badge>
          ))}
        </div>
      )}
    </div>
  )
}
