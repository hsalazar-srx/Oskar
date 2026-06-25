import { useState } from "react"
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
  created_at: string
  originator_username: string
  next_action_users: string[]
}

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

export default function ECNListPage() {
  const navigate = useNavigate()
  const logout = useAuthStore((s) => s.logout)
  const user = useAuthStore((s) => s.user)
  const [statusFilter, setStatusFilter] = useState("")
  const [search, setSearch] = useState("")

  const params: Record<string, string> = {}
  if (statusFilter) params.status = statusFilter
  if (search) params.search = search

  const { data: ecns = [], isLoading, isError } = useQuery({
    queryKey: ["ecns", params],
    queryFn: () => fetchECNs(params),
  })

  const active   = ecns.filter((e) => ![65, 70, 80].includes(e.status)).length
  const overdue  = ecns.filter((e) => ageDays(e.created_at) > 7 && ![65, 70, 80].includes(e.status)).length
  const myAction = ecns.filter((e) => user && e.next_action_users?.includes(user.username)).length

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

      <main className="flex-1 mx-auto w-full max-w-6xl px-6 py-6 space-y-5">
        {/* Stat strip */}
        <div className="grid grid-cols-3 gap-3">
          <StatCard label="Active ECNs"       value={active}   />
          <StatCard label="Require my action" value={myAction} color="info" />
          <StatCard label="Overdue (>7 days)" value={overdue}  color={overdue > 0 ? "warning" : undefined} />
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-2 items-center">
          <div className="relative">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#94a3b8] pointer-events-none" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
            </svg>
            <input
              type="search"
              placeholder="Search title or ECN number…"
              className="h-9 rounded-lg border border-[#d1d9e0] bg-white pl-8 pr-3 text-sm w-64 text-[#0f172a] placeholder:text-[#94a3b8] focus:outline-none focus:border-[#0066cc] focus:ring-2 focus:ring-[#0066cc]/20 transition-all duration-150"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
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
          {(search || statusFilter) && (
            <button
              className="text-xs text-[#94a3b8] hover:text-[#475569] transition-colors duration-150"
              onClick={() => { setSearch(""); setStatusFilter("") }}
            >
              Clear
            </button>
          )}
          <span className="ml-auto text-xs text-[#94a3b8]">
            {ecns.length} result{ecns.length !== 1 ? "s" : ""}
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
                  <TableHead className="w-36 font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3">Number</TableHead>
                  <TableHead className="font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3">Title</TableHead>
                  <TableHead className="w-40 font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3">Status</TableHead>
                  <TableHead className="w-28 font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3 hidden md:table-cell">Originator</TableHead>
                  <TableHead className="w-24 font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3 hidden md:table-cell">Customer</TableHead>
                  <TableHead className="w-32 font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3 hidden lg:table-cell">Next action</TableHead>
                  <TableHead className="w-20 text-right font-semibold text-xs uppercase tracking-wider text-[#94a3b8] py-3">Age</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {ecns.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-20">
                      <div className="flex flex-col items-center gap-2">
                        <div className="w-10 h-10 rounded-full bg-[#f1f5f9] flex items-center justify-center">
                          <svg className="w-5 h-5 text-[#94a3b8]" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/>
                          </svg>
                        </div>
                        <p className="text-sm text-[#94a3b8]">
                          {search || statusFilter ? "No ECNs match your filters." : "No ECNs yet — create the first one."}
                        </p>
                      </div>
                    </TableCell>
                  </TableRow>
                )}
                {ecns.map((ecn) => {
                  const age = ageDays(ecn.created_at)
                  const isOverdue  = age > 7 && ![65, 70, 80].includes(ecn.status)
                  const isMyAction = user && ecn.next_action_users?.includes(user.username)
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
                      <TableCell className="py-3.5">
                        <span className="text-sm text-[#0f172a] line-clamp-1">{ecn.title}</span>
                      </TableCell>
                      <TableCell className="py-3.5">
                        <Badge variant={statusBadgeVariant(ecn.status)}>
                          {statusLabel(ecn.status)}
                        </Badge>
                      </TableCell>
                      <TableCell className="py-3.5 text-xs text-[#475569] hidden md:table-cell">
                        {ecn.originator_username}
                      </TableCell>
                      <TableCell className="py-3.5 text-xs font-mono text-[#475569] hidden md:table-cell">
                        {ecn.customer_number ?? "—"}
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

// ── StatCard ──────────────────────────────────────────────────────────────────

type StatColor = "default" | "info" | "warning" | "success" | "error"

interface StatCardProps {
  label: string
  value: number
  color?: StatColor
}

const STAT_STYLES: Record<StatColor, { card: string; value: string; icon: string }> = {
  default: { card: "border-[#e8ecf0] bg-white",         value: "text-[#0f172a]",  icon: "bg-[#f1f5f9] text-[#94a3b8]" },
  info:    { card: "border-blue-200 bg-[#eff6ff]",       value: "text-[#0066cc]",  icon: "bg-blue-100 text-[#0066cc]" },
  warning: { card: "border-amber-200 bg-amber-50",       value: "text-amber-700",  icon: "bg-amber-100 text-amber-600" },
  success: { card: "border-emerald-200 bg-emerald-50",   value: "text-emerald-700", icon: "bg-emerald-100 text-emerald-600" },
  error:   { card: "border-red-200 bg-red-50",           value: "text-red-600",    icon: "bg-red-100 text-red-500" },
}

function StatCard({ label, value, color = "default" }: StatCardProps) {
  const s = STAT_STYLES[color]
  return (
    <div className={`rounded-xl border px-5 py-4 shadow-[var(--shadow-sm)] ${s.card}`}>
      <p className="text-xs font-semibold uppercase tracking-wider text-[#94a3b8] mb-2">{label}</p>
      <p className={`text-3xl font-bold tabular-nums ${s.value}`}>{value}</p>
    </div>
  )
}
