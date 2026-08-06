import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { useAuthStore } from "@/store/auth"
import {
  fetchBOM, fetchBOMIndented, fetchWhereUsed,
  type BOMHead, type BOMTreeNode, type WhereUsedLine,
} from "@/api/bom"

function formatMovexDate(yyyymmdd: number): string {
  if (yyyymmdd >= 99999999) return "—"
  const s = String(yyyymmdd)
  if (s.length !== 8) return s
  return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`
}

type ViewTab = "lines" | "indented" | "where-used"

const TABS: { key: ViewTab; label: string }[] = [
  { key: "lines", label: "Lines" },
  { key: "indented", label: "Indented" },
  { key: "where-used", label: "Where used" },
]

export default function BOMBrowserPage() {
  const navigate = useNavigate()
  const logout = useAuthStore((s) => s.logout)
  const user = useAuthStore((s) => s.user)

  const [search, setSearch] = useState("")
  const [itemNumber, setItemNumber] = useState<string | null>(null)
  const [includeExpired, setIncludeExpired] = useState(false)
  const [activeTab, setActiveTab] = useState<ViewTab>("lines")

  const { data, isLoading, isFetching, isError, error } = useQuery<BOMHead>({
    queryKey: ["bom", itemNumber, includeExpired],
    queryFn: () => fetchBOM(itemNumber!, { includeExpired }),
    enabled: !!itemNumber,
    retry: 1,
  })

  const indentedQuery = useQuery<BOMTreeNode>({
    queryKey: ["bom-indented", itemNumber],
    queryFn: () => fetchBOMIndented(itemNumber!),
    enabled: !!itemNumber && activeTab === "indented",
    retry: 1,
  })

  const whereUsedQuery = useQuery<WhereUsedLine[]>({
    queryKey: ["bom-where-used", itemNumber],
    queryFn: () => fetchWhereUsed(itemNumber!),
    enabled: !!itemNumber && activeTab === "where-used",
    retry: 1,
  })

  function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = search.trim()
    if (trimmed) {
      setItemNumber(trimmed.toUpperCase())
      setActiveTab("lines")
    }
  }

  const notFound = isError && (error as any)?.response?.status === 404

  return (
    <div className="min-h-screen bg-[#f5f7fa] flex flex-col">
      {/* Top nav */}
      <header className="sticky top-0 z-[1020] border-b border-[#e8ecf0] bg-white shadow-[var(--shadow-xs)] px-6 h-14 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-md bg-[#0066cc] flex items-center justify-center shrink-0">
            <span className="text-white font-bold text-xs">O</span>
          </div>
          <span className="font-semibold tracking-tight text-[#0f172a]">Oskar</span>
          <span className="text-[#d1d9e0]">/</span>
          <span className="text-sm text-[#94a3b8]">BOM Browser</span>
        </div>
        <div className="flex items-center gap-3">
          {user && (
            <span className="text-xs text-[#94a3b8] hidden sm:block">
              <span className="font-medium text-[#475569]">{user.username}</span>
            </span>
          )}
          <button
            onClick={() => navigate("/ecn")}
            className="text-xs text-[#94a3b8] hover:text-[#475569] transition-colors duration-150"
          >
            ECNs
          </button>
          <button
            onClick={logout}
            className="text-xs text-[#94a3b8] hover:text-[#475569] transition-colors duration-150"
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-6xl px-6 py-6 space-y-5">
        {/* Search bar */}
        <form onSubmit={handleSearch} className="flex flex-wrap items-center gap-2">
          <input
            type="search"
            placeholder="Item number (e.g. LF100001)…"
            className="h-9 rounded-lg border border-[#d1d9e0] bg-white px-3 text-sm w-64 font-mono text-[#0f172a] placeholder:text-[#94a3b8] placeholder:font-sans focus:outline-none focus:border-[#0066cc] focus:ring-2 focus:ring-[#0066cc]/20 transition-all duration-150"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Item number"
          />
          <Button type="submit" size="sm">Browse</Button>
          {itemNumber && (
            <label className="flex items-center gap-1.5 text-xs text-[#475569] ml-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={includeExpired}
                onChange={(e) => setIncludeExpired(e.target.checked)}
              />
              Include expired lines
            </label>
          )}
        </form>

        {!itemNumber && (
          <div className="flex flex-col items-center justify-center py-20 text-center gap-2">
            <div className="w-10 h-10 rounded-full bg-[#f1f5f9] flex items-center justify-center">
              <svg className="w-5 h-5 text-[#94a3b8]" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z" />
              </svg>
            </div>
            <p className="text-sm text-[#94a3b8]">Enter an item number to browse its BOM.</p>
          </div>
        )}

        {itemNumber && activeTab === "lines" && (isLoading || isFetching) && (
          <div className="flex items-center justify-center py-20">
            <Spinner size="lg" />
          </div>
        )}

        {itemNumber && activeTab === "lines" && isError && notFound && (
          <div className="flex items-center gap-2.5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            No BOM found for item {itemNumber}.
          </div>
        )}

        {itemNumber && activeTab === "lines" && isError && !notFound && (
          <div className="flex items-center gap-2.5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            Failed to load BOM — the ERP system may be unavailable. Try again shortly.
          </div>
        )}

        {itemNumber && data && !isLoading && (
          <div className="space-y-4">
            <div className="rounded-xl border border-[#e8ecf0] bg-white px-5 py-4 shadow-[var(--shadow-sm)] flex items-start justify-between gap-4">
              <div>
                <div className="flex items-baseline gap-3">
                  <span className="font-mono text-lg font-semibold text-[#0066cc]">{data.item_number}</span>
                  <span className="text-sm text-[#0f172a]">{data.description}</span>
                </div>
                <div className="mt-1 flex gap-4 text-xs text-[#94a3b8]">
                  <span>Facility: <span className="font-mono text-[#475569]">{data.facility}</span></span>
                  <span>Structure: <span className="font-mono text-[#475569]">{data.structure_type}</span></span>
                  <span>{data.lines.length} line{data.lines.length !== 1 ? "s" : ""}</span>
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => navigate(`/bom/compare?left=${encodeURIComponent(data.item_number)}&leftFacility=${encodeURIComponent(data.facility)}`)}
              >
                Compare against…
              </Button>
            </div>

            {/* Tab bar */}
            <div className="flex gap-1 border-b border-[#e8ecf0]">
              {TABS.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors duration-150 ${
                    activeTab === tab.key
                      ? "border-[#0066cc] text-[#0066cc]"
                      : "border-transparent text-[#94a3b8] hover:text-[#475569]"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {activeTab === "lines" && (
              <div className="rounded-xl border border-[#e8ecf0] bg-white overflow-hidden shadow-[var(--shadow-sm)]">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-[#f8fafc] hover:bg-[#f8fafc] border-b border-[#e8ecf0]">
                      <TableHead className="w-16 font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3">Seq</TableHead>
                      <TableHead className="font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3">Component</TableHead>
                      <TableHead className="font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3">Description</TableHead>
                      <TableHead className="w-16 font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3">Op</TableHead>
                      <TableHead className="w-20 text-right font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3">Qty</TableHead>
                      <TableHead className="w-16 font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3">UOM</TableHead>
                      <TableHead className="w-28 font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3 hidden md:table-cell">Effective</TableHead>
                      <TableHead className="w-28 font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3 hidden md:table-cell">Expires</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.lines.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={8} className="text-center py-16 text-sm text-[#94a3b8]">
                          No lines match the current filter.
                        </TableCell>
                      </TableRow>
                    )}
                    {data.lines.map((line) => (
                      <TableRow key={`${line.sequence_number}-${line.operation_number}`} className="border-b border-[#f1f5f9] last:border-0 hover:bg-[#f8fafc]">
                        <TableCell className="py-3 text-xs font-mono text-[#94a3b8] tabular-nums">{line.sequence_number}</TableCell>
                        <TableCell className="py-3 font-mono text-sm text-[#0f172a]">{line.component_number}</TableCell>
                        <TableCell className="py-3 text-sm text-[#475569]">{line.description}</TableCell>
                        <TableCell className="py-3 text-xs font-mono text-[#94a3b8] tabular-nums">{line.operation_number}</TableCell>
                        <TableCell className="py-3 text-right text-sm tabular-nums text-[#0f172a]">{line.quantity}</TableCell>
                        <TableCell className="py-3 text-xs text-[#94a3b8]">{line.unit_of_measure}</TableCell>
                        <TableCell className="py-3 text-xs text-[#94a3b8] tabular-nums hidden md:table-cell">{formatMovexDate(line.from_date)}</TableCell>
                        <TableCell className="py-3 text-xs text-[#94a3b8] tabular-nums hidden md:table-cell">{formatMovexDate(line.to_date)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}

            {activeTab === "indented" && (
              <div className="rounded-xl border border-[#e8ecf0] bg-white overflow-hidden shadow-[var(--shadow-sm)] p-2">
                {indentedQuery.isLoading && (
                  <div className="flex items-center justify-center py-16">
                    <Spinner size="lg" />
                  </div>
                )}
                {indentedQuery.isError && (
                  <div className="flex items-center gap-2.5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 m-2 text-sm text-red-700">
                    {(indentedQuery.error as any)?.response?.status === 422
                      ? "Could not assemble the BOM tree — the source data may contain a cycle."
                      : "Failed to load the multi-level explosion — the ERP system may be unavailable."}
                  </div>
                )}
                {indentedQuery.data && (
                  <BOMTreeView root={indentedQuery.data} />
                )}
              </div>
            )}

            {activeTab === "where-used" && (
              <div className="rounded-xl border border-[#e8ecf0] bg-white overflow-hidden shadow-[var(--shadow-sm)]">
                {whereUsedQuery.isLoading && (
                  <div className="flex items-center justify-center py-16">
                    <Spinner size="lg" />
                  </div>
                )}
                {whereUsedQuery.isError && (
                  <div className="flex items-center gap-2.5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 m-4 text-sm text-red-700">
                    Failed to load where-used data — the ERP system may be unavailable.
                  </div>
                )}
                {whereUsedQuery.data && (
                  <WhereUsedTable lines={whereUsedQuery.data} />
                )}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  )
}

// ── Indented tree (Slice B) ─────────────────────────────────────────────────────

function BOMTreeView({ root }: { root: BOMTreeNode }) {
  // Root and its immediate children start expanded; deeper levels start
  // collapsed so a large explosion doesn't render fully open by default.
  const [expanded, setExpanded] = useState<Set<string>>(() => {
    const initial = new Set<string>(["root"])
    root.children.forEach((_, i) => initial.add(`root-${i}`))
    return initial
  })

  function toggle(path: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  return (
    <div className="text-sm">
      <BOMTreeRow node={root} path="root" depth={0} expanded={expanded} onToggle={toggle} isRoot />
    </div>
  )
}

function BOMTreeRow({
  node, path, depth, expanded, onToggle, isRoot = false,
}: {
  node: BOMTreeNode
  path: string
  depth: number
  expanded: Set<string>
  onToggle: (path: string) => void
  isRoot?: boolean
}) {
  const hasChildren = node.children.length > 0
  const isOpen = expanded.has(path)

  return (
    <div>
      <div
        className={`flex items-center gap-2 py-1.5 px-2 rounded-md hover:bg-[#f8fafc] ${hasChildren ? "cursor-pointer" : ""}`}
        style={{ paddingLeft: `${depth * 20 + 8}px` }}
        onClick={hasChildren ? () => onToggle(path) : undefined}
      >
        {hasChildren ? (
          <span className={`inline-block w-3 text-[#94a3b8] transition-transform duration-150 ${isOpen ? "rotate-90" : ""}`}>
            ▶
          </span>
        ) : (
          <span className="inline-block w-3" />
        )}
        <span className="font-mono text-[#0f172a]">{node.component_number}</span>
        {node.description && <span className="text-[#94a3b8] text-xs">{node.description}</span>}
        {node.is_phantom && (
          <span className="rounded-full bg-amber-100 text-amber-700 text-[10px] px-1.5 py-0.5 font-medium">phantom</span>
        )}
        {!isRoot && (
          <span className="ml-auto text-xs tabular-nums text-[#475569]">
            qty {node.quantity} · cum {node.cumulative_quantity}
          </span>
        )}
      </div>
      {hasChildren && isOpen && (
        <div>
          {node.children.map((child, i) => (
            <BOMTreeRow
              key={`${path}-${i}`}
              node={child}
              path={`${path}-${i}`}
              depth={depth + 1}
              expanded={expanded}
              onToggle={onToggle}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ── Where-used table (Slice B) ──────────────────────────────────────────────────

function WhereUsedTable({ lines }: { lines: WhereUsedLine[] }) {
  if (lines.length === 0) {
    return (
      <div className="text-center py-16 text-sm text-[#94a3b8]">
        This component is not used in any active BOM.
      </div>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow className="bg-[#f8fafc] hover:bg-[#f8fafc] border-b border-[#e8ecf0]">
          <TableHead className="font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3">Parent item</TableHead>
          <TableHead className="w-20 font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3">Structure</TableHead>
          <TableHead className="w-16 font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3">Seq</TableHead>
          <TableHead className="w-16 font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3">Op</TableHead>
          <TableHead className="w-20 text-right font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3">Qty</TableHead>
          <TableHead className="w-28 font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3 hidden md:table-cell">Effective</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {lines.map((line) => (
          <TableRow
            key={`${line.parent_item}-${line.sequence_number}-${line.operation_number}`}
            className="border-b border-[#f1f5f9] last:border-0 hover:bg-[#f8fafc]"
          >
            <TableCell className="py-3 font-mono text-sm text-[#0f172a]">{line.parent_item}</TableCell>
            <TableCell className="py-3 text-xs font-mono text-[#94a3b8]">{line.structure_type}</TableCell>
            <TableCell className="py-3 text-xs font-mono text-[#94a3b8] tabular-nums">{line.sequence_number}</TableCell>
            <TableCell className="py-3 text-xs font-mono text-[#94a3b8] tabular-nums">{line.operation_number}</TableCell>
            <TableCell className="py-3 text-right text-sm tabular-nums text-[#0f172a]">{line.quantity}</TableCell>
            <TableCell className="py-3 text-xs text-[#94a3b8] tabular-nums hidden md:table-cell">{formatMovexDate(line.from_date)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
