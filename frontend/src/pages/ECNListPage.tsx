import { useState, useMemo } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Spinner } from "@/components/ui/spinner"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { useAuthStore } from "@/store/auth"
import axiosInstance from "@/api/axios"
import { statusLabel, statusBadgeVariant } from "@/lib/ecn-status"
import { ageDays } from "@/lib/ecn-workflow"

interface ECNSummary {
  id: string
  ecn_number: string
  title: string
  status: number
  facility: string
  customer_number: string | null
  customer_name: string | null
  customer_ecn_refs: string | null
  created_at: string
  originator_username: string
  next_action_users: string[]
}

type SortField = "ecn_number" | "created_at" | "status" | "originator_username" | "customer_number"
type SortDir = "asc" | "desc"

async function fetchECNs(params: Record<string, string>) {
  const q = new URLSearchParams(params).toString()
  const { data } = await axiosInstance.get(`/api/v1/ecn/?${q}`)
  return data as ECNSummary[]
}

const STATUS_OPTIONS = [
  { value: "0",  label: "Draft" },
  { value: "30", label: "Engineering Review" },
  { value: "40", label: "Management Review" },
  { value: "25", label: "DC Approved" },
  { value: "50", label: "Approved" },
  { value: "60", label: "Implemented" },
  { value: "65", label: "Rejected" },
  { value: "70", label: "Closed" },
  { value: "90", label: "On Hold" },
]

const TERMINAL = [60, 65, 70, 80]

export default function ECNListPage() {
  const navigate = useNavigate()
  const logout = useAuthStore((s) => s.logout)
  const user = useAuthStore((s) => s.user)

  // Filter state
  const [statusFilter, setStatusFilter]       = useState("")
  const [search, setSearch]                   = useState("")
  const [customerFilter, setCustomerFilter]   = useState("")
  const [originatorFilter, setOriginatorFilter] = useState("")
  const [nextActionFilter, setNextActionFilter] = useState("")
  const [myActionOnly, setMyActionOnly]       = useState(false)
  const [overdueOnly, setOverdueOnly]         = useState(false)
  const [activeOnly, setActiveOnly]           = useState(false)

  // Sort state
  const [sortField, setSortField] = useState<SortField>("created_at")
  const [sortDir, setSortDir]     = useState<SortDir>("desc")

  // Build server-side query params (search, status, sort only — stat-card filters are client-side)
  const params: Record<string, string> = {
    sort_by: sortField,
    sort_dir: sortDir,
    limit: "200",
  }
  if (statusFilter) params.status = statusFilter
  if (search)       params.search  = search

  const { data: ecns = [], isLoading, isError } = useQuery({
    queryKey: ["ecns", params],
    queryFn: () => fetchECNs(params),
    staleTime: 30_000,
    retry: 1,
  })

  // Build distinct values for client-side dropdown filters
  const distinctCustomers  = useMemo(() =>
    [...new Set(ecns.map((e) => e.customer_number).filter(Boolean))].sort() as string[]
  , [ecns])
  const distinctOriginators = useMemo(() =>
    [...new Set(ecns.map((e) => e.originator_username))].sort()
  , [ecns])
  const distinctNextActions = useMemo(() => {
    const all: string[] = []
    ecns.forEach((e) => e.next_action_users?.forEach((u) => all.push(u)))
    return [...new Set(all)].sort()
  }, [ecns])

  // Apply client-side filters (column dropdowns + stat-card toggles)
  const filtered = useMemo(() => {
    return ecns.filter((e) => {
      if (customerFilter && e.customer_number !== customerFilter) return false
      if (originatorFilter && e.originator_username !== originatorFilter) return false
      if (nextActionFilter && !e.next_action_users?.includes(nextActionFilter)) return false
      if (activeOnly && TERMINAL.includes(e.status)) return false
      if (overdueOnly && !(ageDays(e.created_at) > 7 && !TERMINAL.includes(e.status))) return false
      if (myActionOnly && !(user && e.next_action_users?.includes(user.username))) return false
      return true
    })
  }, [ecns, customerFilter, originatorFilter, nextActionFilter, activeOnly, overdueOnly, myActionOnly, user])

  const active   = ecns.filter((e) => !TERMINAL.includes(e.status)).length
  const overdue  = ecns.filter((e) => ageDays(e.created_at) > 7 && !TERMINAL.includes(e.status)).length
  const myAction = ecns.filter((e) => user && e.next_action_users?.includes(user.username)).length

  function handleSort(field: SortField) {
    if (sortField === field) {
      setSortDir(sortDir === "asc" ? "desc" : "asc")
    } else {
      setSortField(field)
      setSortDir("desc")
    }
  }

  function clearAll() {
    setSearch("")
    setStatusFilter("")
    setCustomerFilter("")
    setOriginatorFilter("")
    setNextActionFilter("")
    setMyActionOnly(false)
    setOverdueOnly(false)
    setActiveOnly(false)
  }

  const hasFilters = search || statusFilter || customerFilter || originatorFilter || nextActionFilter || myActionOnly || overdueOnly || activeOnly

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
          <span className="text-sm text-[#94a3b8]">Engineering Changes</span>
        </div>
        <div className="flex items-center gap-3">
          {user && (
            <span className="text-xs text-[#94a3b8] hidden sm:block">
              <span className="font-medium text-[#475569]">{user.username}</span>
            </span>
          )}
          <Button size="sm" onClick={() => navigate("/ecn/new")}>
            + New ECN
          </Button>
          <button
            onClick={logout}
            className="text-xs text-[#94a3b8] hover:text-[#475569] transition-colors duration-150"
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-7xl px-6 py-6 space-y-5">
        {/* Stat strip — clickable toggles */}
        <div className="grid grid-cols-3 gap-3">
          <StatCard
            label="Active ECNs"
            value={active}
            color="success"
            active={activeOnly}
            onClick={() => { setActiveOnly(!activeOnly); setMyActionOnly(false); setOverdueOnly(false) }}
          />
          <StatCard
            label="Require my action"
            value={myAction}
            color="info"
            active={myActionOnly}
            onClick={() => { setMyActionOnly(!myActionOnly); setOverdueOnly(false); setActiveOnly(false) }}
          />
          <StatCard
            label="Overdue (>7 days)"
            value={overdue}
            color={overdue > 0 ? "warning" : undefined}
            active={overdueOnly}
            onClick={() => { setOverdueOnly(!overdueOnly); setMyActionOnly(false); setActiveOnly(false) }}
          />
        </div>

        {/* Filter row */}
        <div className="flex flex-wrap gap-2 items-center">
          {/* Full-text search */}
          <div className="relative">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#94a3b8] pointer-events-none" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
            </svg>
            <input
              type="search"
              placeholder="Search ECNs…"
              className="h-9 rounded-lg border border-[#d1d9e0] bg-white pl-8 pr-3 text-sm w-64 text-[#0f172a] placeholder:text-[#94a3b8] focus:outline-none focus:border-[#0066cc] focus:ring-2 focus:ring-[#0066cc]/20 transition-all duration-150"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          {/* Status filter */}
          <select
            className="h-9 rounded-lg border border-[#d1d9e0] bg-white px-3 text-sm text-[#475569] focus:outline-none focus:border-[#0066cc] focus:ring-2 focus:ring-[#0066cc]/20 transition-all duration-150"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map(({ value, label }) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>

          {/* Customer column filter */}
          <select
            className="h-9 rounded-lg border border-[#d1d9e0] bg-white px-3 text-sm text-[#475569] focus:outline-none focus:border-[#0066cc] focus:ring-2 focus:ring-[#0066cc]/20 transition-all duration-150"
            value={customerFilter}
            onChange={(e) => setCustomerFilter(e.target.value)}
          >
            <option value="">All customers</option>
            {distinctCustomers.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>

          {/* Originator column filter */}
          <select
            className="h-9 rounded-lg border border-[#d1d9e0] bg-white px-3 text-sm text-[#475569] focus:outline-none focus:border-[#0066cc] focus:ring-2 focus:ring-[#0066cc]/20 transition-all duration-150"
            value={originatorFilter}
            onChange={(e) => setOriginatorFilter(e.target.value)}
          >
            <option value="">All originators</option>
            {distinctOriginators.map((o) => (
              <option key={o} value={o}>{o}</option>
            ))}
          </select>

          {/* Next action column filter */}
          <select
            className="h-9 rounded-lg border border-[#d1d9e0] bg-white px-3 text-sm text-[#475569] focus:outline-none focus:border-[#0066cc] focus:ring-2 focus:ring-[#0066cc]/20 transition-all duration-150"
            value={nextActionFilter}
            onChange={(e) => setNextActionFilter(e.target.value)}
          >
            <option value="">All next actions</option>
            {distinctNextActions.map((u) => (
              <option key={u} value={u}>{u}</option>
            ))}
          </select>

          {hasFilters && (
            <button
              className="text-xs text-[#94a3b8] hover:text-[#475569] transition-colors duration-150"
              onClick={clearAll}
            >
              Clear all
            </button>
          )}
          <span className="ml-auto text-xs text-[#94a3b8]">
            {filtered.length} result{filtered.length !== 1 ? "s" : ""}
          </span>
        </div>

        {/* Content */}
        {isLoading && (
          <div className="flex items-center justify-center py-20">
            <Spinner size="lg" />
          </div>
        )}
        {isError && (
          <div className="flex items-center gap-2.5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <svg className="w-4 h-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clipRule="evenodd"/>
            </svg>
            Failed to load ECNs — check that the backend is running.
          </div>
        )}
        {!isLoading && !isError && (
          <div className="rounded-xl border border-[#e8ecf0] bg-white overflow-hidden shadow-[var(--shadow-sm)]">
            <Table>
              <TableHeader>
                <TableRow className="bg-[#f8fafc] hover:bg-[#f8fafc] border-b border-[#e8ecf0]">
                  <SortableHead field="ecn_number" label="Number" current={sortField} dir={sortDir} onSort={handleSort} className="w-36" />
                  <TableHead className="w-24 font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3 hidden md:table-cell">Customer</TableHead>
                  <TableHead className="font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3">Title</TableHead>
                  <TableHead className="w-24 font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3 hidden sm:table-cell">Cust. ECN</TableHead>
                  <SortableHead field="status" label="Status" current={sortField} dir={sortDir} onSort={handleSort} className="w-40" />
                  <SortableHead field="originator_username" label="Originator" current={sortField} dir={sortDir} onSort={handleSort} className="w-28 hidden md:table-cell" />
                  <TableHead className="w-32 font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3 hidden lg:table-cell">Next action</TableHead>
                  <SortableHead field="created_at" label="Entry Date" current={sortField} dir={sortDir} onSort={handleSort} className="w-28 hidden lg:table-cell" />
                  <TableHead className="w-20 text-right font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3">Age</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={9} className="text-center py-20">
                      <div className="flex flex-col items-center gap-2">
                        <div className="w-10 h-10 rounded-full bg-[#f1f5f9] flex items-center justify-center">
                          <svg className="w-5 h-5 text-[#94a3b8]" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/>
                          </svg>
                        </div>
                        <p className="text-sm text-[#94a3b8]">
                          {hasFilters ? "No ECNs match your filters." : "No ECNs yet — create the first one."}
                        </p>
                      </div>
                    </TableCell>
                  </TableRow>
                )}
                {filtered.map((ecn) => {
                  const age = ageDays(ecn.created_at)
                  const isOverdue  = age > 7 && !TERMINAL.includes(ecn.status)
                  const isMyAction = user && ecn.next_action_users?.includes(user.username)
                  const custEcnTags = ecn.customer_ecn_refs
                    ? ecn.customer_ecn_refs.split(",").map((s) => s.trim()).filter(Boolean)
                    : []
                  const entryDate = new Date(ecn.created_at).toLocaleDateString("en-AU", {
                    day: "2-digit", month: "short", year: "numeric",
                  })
                  return (
                    <TableRow
                      key={ecn.id}
                      className={`cursor-pointer transition-colors duration-150 border-b border-[#f1f5f9] last:border-0 ${
                        isMyAction ? "bg-[#eff6ff] hover:bg-[#dbeafe]/60" : "hover:bg-[#f8fafc]"
                      }`}
                      onClick={() => navigate(`/ecn/${ecn.id}`)}
                    >
                      <TableCell className="py-3.5">
                        <Link
                          to={`/ecn/${ecn.id}`}
                          onClick={(e) => e.stopPropagation()}
                          className="font-mono text-sm font-semibold text-[#0066cc] hover:text-[#0052a3] hover:underline"
                        >
                          {ecn.ecn_number}
                        </Link>
                      </TableCell>
                      <TableCell className="py-3.5 hidden md:table-cell">
                        <div className="flex flex-col">
                          <span className="text-sm text-[#0f172a] font-medium leading-tight">
                            {ecn.customer_name ?? ecn.customer_number ?? "—"}
                          </span>
                          {ecn.customer_name && ecn.customer_number && (
                            <span className="text-[10px] font-mono text-[#94a3b8]">{ecn.customer_number}</span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="py-3.5">
                        <span className="text-sm text-[#0f172a] line-clamp-1">{ecn.title}</span>
                      </TableCell>
                      <TableCell className="py-3.5 hidden sm:table-cell">
                        {custEcnTags.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {custEcnTags.slice(0, 3).map((tag) => (
                              <span key={tag} className="inline-block rounded-full bg-[#f1f5f9] px-2 py-0.5 text-[10px] font-mono text-[#64748b]">
                                {tag}
                              </span>
                            ))}
                            {custEcnTags.length > 3 && (
                              <span className="text-[10px] text-[#94a3b8]">+{custEcnTags.length - 3}</span>
                            )}
                          </div>
                        ) : (
                          <span className="text-xs text-[#cbd5e1]">—</span>
                        )}
                      </TableCell>
                      <TableCell className="py-3.5">
                        <Badge variant={statusBadgeVariant(ecn.status)}>
                          {statusLabel(ecn.status)}
                        </Badge>
                      </TableCell>
                      <TableCell className="py-3.5 text-xs text-[#475569] hidden md:table-cell">
                        {ecn.originator_username}
                      </TableCell>
                      <TableCell className="py-3.5 hidden lg:table-cell">
                        {ecn.next_action_users?.length > 0 ? (
                          <span className="text-xs text-[#0066cc] font-medium">
                            {ecn.next_action_users.join(", ")}
                          </span>
                        ) : (
                          <span className="text-xs text-[#cbd5e1]">—</span>
                        )}
                      </TableCell>
                      <TableCell className="py-3.5 text-xs text-[#94a3b8] hidden lg:table-cell tabular-nums">
                        {entryDate}
                      </TableCell>
                      <TableCell className="py-3.5 text-right">
                        <span className={`text-xs tabular-nums font-mono ${isOverdue ? "text-red-500 font-semibold" : "text-[#94a3b8]"}`}>
                          {age}d
                        </span>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </main>
    </div>
  )
}

// ── SortableHead ──────────────────────────────────────────────────────────────

interface SortableHeadProps {
  field: SortField
  label: string
  current: SortField
  dir: SortDir
  onSort: (f: SortField) => void
  className?: string
}

function SortableHead({ field, label, current, dir, onSort, className = "" }: SortableHeadProps) {
  const isActive = current === field
  return (
    <TableHead
      className={`font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3 cursor-pointer select-none hover:text-[#475569] transition-colors ${className}`}
      onClick={() => onSort(field)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        <span className={`transition-opacity ${isActive ? "opacity-100" : "opacity-30"}`}>
          {isActive && dir === "asc" ? "↑" : "↓"}
        </span>
      </span>
    </TableHead>
  )
}

// ── StatCard ──────────────────────────────────────────────────────────────────

type StatColor = "default" | "info" | "warning" | "success" | "error"

interface StatCardProps {
  label: string
  value: number
  color?: StatColor
  active?: boolean
  onClick?: () => void
}

const STAT_STYLES: Record<StatColor, { card: string; activeCard: string; value: string; icon: string }> = {
  default: { card: "border-[#e8ecf0] bg-white",       activeCard: "ring-2 ring-[#0f172a]",      value: "text-[#0f172a]",   icon: "bg-[#f1f5f9] text-[#94a3b8]" },
  info:    { card: "border-blue-200 bg-[#eff6ff]",     activeCard: "ring-2 ring-[#0066cc]",       value: "text-[#0066cc]",   icon: "bg-blue-100 text-[#0066cc]" },
  warning: { card: "border-amber-200 bg-amber-50",     activeCard: "ring-2 ring-amber-500",       value: "text-amber-700",   icon: "bg-amber-100 text-amber-600" },
  success: { card: "border-emerald-200 bg-emerald-50", activeCard: "ring-2 ring-emerald-500",     value: "text-emerald-700", icon: "bg-emerald-100 text-emerald-600" },
  error:   { card: "border-red-200 bg-red-50",         activeCard: "ring-2 ring-red-500",         value: "text-red-600",     icon: "bg-red-100 text-red-500" },
}

function StatCard({ label, value, color = "default", active = false, onClick }: StatCardProps) {
  const s = STAT_STYLES[color]
  const clickable = !!onClick
  return (
    <div
      className={`rounded-xl border px-5 py-4 shadow-[var(--shadow-sm)] transition-all duration-150 ${s.card} ${active ? s.activeCard : ""} ${clickable ? "cursor-pointer hover:shadow-md" : ""}`}
      onClick={onClick}
    >
      <p className="text-xs font-semibold uppercase tracking-wider text-[#94a3b8] mb-2">{label}</p>
      <p className={`text-3xl font-bold tabular-nums ${s.value}`}>{value}</p>
      {clickable && (
        <p className="text-[10px] text-[#94a3b8] mt-1">{active ? "Click to clear filter" : "Click to filter"}</p>
      )}
    </div>
  )
}
