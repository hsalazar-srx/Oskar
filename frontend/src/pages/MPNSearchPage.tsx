import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Spinner } from "@/components/ui/spinner"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useAuthStore } from "@/store/auth"
import { searchMpn, type MpnSearchField, type MpnSearchHit } from "@/api/mpn"

const FIELD_OPTIONS: { value: MpnSearchField; label: string }[] = [
  { value: "mpn", label: "MPN" },
  { value: "item", label: "Item number" },
  { value: "mfr", label: "Manufacturer" },
]

export default function MPNSearchPage() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)

  const [query, setQuery] = useState("")
  const [field, setField] = useState<MpnSearchField>("mpn")
  const [submittedQuery, setSubmittedQuery] = useState("")
  const [selected, setSelected] = useState<MpnSearchHit | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ["mpn-search", submittedQuery, field],
    queryFn: () => searchMpn({ q: submittedQuery, field }),
    enabled: submittedQuery.length > 0,
    staleTime: 30_000,
    retry: 1,
  })

  function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    setSubmittedQuery(query.trim())
  }

  const results = data?.results ?? []

  return (
    <div className="min-h-screen bg-[#f5f7fa] flex flex-col">
      <header className="sticky top-0 z-[1020] border-b border-[#e8ecf0] bg-white shadow-[var(--shadow-xs)] px-6 h-14 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2.5">
          <button onClick={() => navigate("/ecn")} className="w-7 h-7 rounded-md bg-[#0066cc] flex items-center justify-center shrink-0">
            <span className="text-white font-bold text-xs">O</span>
          </button>
          <span className="font-semibold tracking-tight text-[#0f172a]">Oskar</span>
          <span className="text-[#d1d9e0]">/</span>
          <span className="text-sm text-[#94a3b8]">MPN Search</span>
        </div>
        <div className="flex items-center gap-3">
          {user && (
            <span className="text-xs text-[#94a3b8] hidden sm:block">
              <span className="font-medium text-[#475569]">{user.username}</span>
            </span>
          )}
          <button
            onClick={() => navigate("/ecn")}
            className="h-9 px-3 rounded-lg border border-[#d1d9e0] bg-white text-sm text-[#475569] hover:bg-[#f5f7fa] transition-colors duration-150"
          >
            Back to ECNs
          </button>
        </div>
      </header>

      <main className="flex-1 px-6 py-6 max-w-5xl w-full mx-auto">
        <h1 className="text-lg font-semibold text-[#0f172a] mb-1">MPN Search</h1>
        <p className="text-sm text-[#64748b] mb-4">
          Search the Oskar MPN master (item_mpns). Use <code className="font-mono">*</code> as a
          wildcard, e.g. <code className="font-mono">STM32*</code>.
        </p>

        <form onSubmit={handleSearch} className="flex gap-2 mb-5">
          <input
            type="text"
            aria-label="MPN search query"
            placeholder="STM32*"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="flex-1 h-10 rounded-lg border border-[#d1d9e0] bg-white px-3 text-sm text-[#0f172a] focus:outline-none focus:border-[#0066cc] focus:ring-2 focus:ring-[#0066cc]/20 transition-all duration-150"
          />
          <select
            aria-label="Search field"
            value={field}
            onChange={(e) => setField(e.target.value as MpnSearchField)}
            className="h-10 rounded-lg border border-[#d1d9e0] bg-white px-3 text-sm text-[#475569] focus:outline-none focus:border-[#0066cc] focus:ring-2 focus:ring-[#0066cc]/20 transition-all duration-150"
          >
            {FIELD_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <button
            type="submit"
            className="h-10 px-4 rounded-lg bg-[#0066cc] text-white text-sm font-medium hover:bg-[#0052a3] transition-colors duration-150"
          >
            Search
          </button>
        </form>

        {isLoading && (
          <div className="flex justify-center py-10"><Spinner /></div>
        )}

        {isError && (
          <p className="text-sm text-red-600">Search failed. Try again.</p>
        )}

        {!isLoading && submittedQuery && results.length === 0 && (
          <p className="text-sm text-[#64748b]">No MPNs found for "{submittedQuery}".</p>
        )}

        {results.length > 0 && (
          <div className="bg-white rounded-lg border border-[#e8ecf0] overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Item Number</TableHead>
                  <TableHead>Supplier</TableHead>
                  <TableHead>MPN</TableHead>
                  <TableHead>Manufacturer</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {results.map((hit) => (
                  <TableRow
                    key={hit.id}
                    onClick={() => setSelected(hit)}
                    className="cursor-pointer hover:bg-[#f5f7fa]"
                  >
                    <TableCell className="font-mono text-sm">{hit.item_number}</TableCell>
                    <TableCell className="text-sm text-[#64748b]">{hit.supplier_number || "—"}</TableCell>
                    <TableCell className="font-mono text-sm">{hit.mpn}</TableCell>
                    <TableCell className="text-sm">{hit.manufacturer_canonical || hit.manufacturer_name || "—"}</TableCell>
                    <TableCell><MpnChips hit={hit} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {data && (
          <p className="text-xs text-[#94a3b8] mt-3">
            {data.total} result{data.total === 1 ? "" : "s"}
          </p>
        )}
      </main>

      <Sheet open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>
        <SheetContent>
          {selected && (
            <>
              <SheetHeader>
                <SheetTitle className="font-mono">{selected.mpn}</SheetTitle>
                <SheetDescription>Item {selected.item_number}</SheetDescription>
              </SheetHeader>
              <div className="px-4 pb-4 space-y-4">
                <MpnChips hit={selected} />
                <dl className="text-sm space-y-2">
                  <div className="flex justify-between">
                    <dt className="text-[#64748b]">Item number</dt>
                    <dd className="font-mono">{selected.item_number}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-[#64748b]">Supplier</dt>
                    <dd>{selected.supplier_number || "—"}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-[#64748b]">Manufacturer (raw)</dt>
                    <dd>{selected.manufacturer_name || "—"}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-[#64748b]">Manufacturer (canonical)</dt>
                    <dd>{selected.manufacturer_canonical || "—"}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-[#64748b]">End effective date</dt>
                    <dd>{selected.end_effective_date || "None (open-ended)"}</dd>
                  </div>
                </dl>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}

// ── Chips ─────────────────────────────────────────────────────────────────────
// Same rounded-pill chip pattern as MPNRow in ECNItemPanel.tsx (default badge +
// lifecycle-style chips), reused here for consistency.

function MpnChips({ hit }: { hit: MpnSearchHit }) {
  const isCurrent = hit.end_effective_date === null
  const manufacturerMiss =
    hit.manufacturer_name !== null &&
    hit.manufacturer_canonical !== null &&
    hit.manufacturer_name === hit.manufacturer_canonical

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {hit.is_default && (
        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-700 shrink-0">Default</span>
      )}
      <span
        className={
          "text-[10px] font-semibold px-1.5 py-0.5 rounded-full shrink-0 uppercase " +
          (isCurrent ? "bg-green-100 text-green-700" : "bg-neutral-100 text-neutral-500")
        }
      >
        {isCurrent ? "Current" : "Superseded"}
      </span>
      {manufacturerMiss && (
        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 shrink-0">
          Synonym miss
        </span>
      )}
    </div>
  )
}
