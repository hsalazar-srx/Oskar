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
    <div className="min-h-screen bg-neutral-50 flex flex-col">
      {/* Top nav */}
      <header className="sticky top-0 z-[1020] border-b bg-white shadow-sm px-6 h-14 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <span className="font-semibold tracking-tight text-neutral-900">Oskar</span>
          <span className="text-neutral-300">/</span>
          <span className="text-sm text-neutral-500">Engineering Changes</span>
        </div>
        <div className="flex items-center gap-4">
          {user && (
            <span className="text-xs text-neutral-400 hidden sm:block">
              Signed in as <span className="font-medium text-neutral-600">{user.username}</span>
            </span>
          )}
          <Button size="sm" onClick={() => navigate("/ecn/new")}>
            + New ECN
          </Button>
          <button
            onClick={logout}
            className="text-xs text-neutral-400 hover:text-neutral-700 transition-colors duration-[150ms]"
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-6xl px-6 py-6 space-y-5">
        {/* Stat strip */}
        <div className="grid grid-cols-3 gap-3">
          <StatCard label="Active ECNs" value={active} />
          <StatCard label="Require my action" value={myAction} color="info" />
          <StatCard label="Overdue (>7 days)" value={overdue} color={overdue > 0 ? "warning" : undefined} />
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-2 items-center">
          <input
            type="search"
            placeholder="Search title or ECN number…"
            className="h-9 rounded-md border border-neutral-200 bg-white px-3 text-sm w-64 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent transition-shadow duration-[150ms]"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            className="h-9 rounded-md border border-neutral-200 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900 transition-shadow duration-[150ms]"
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
              className="text-xs text-neutral-400 hover:text-neutral-700 transition-colors duration-[150ms]"
              onClick={() => { setSearch(""); setStatusFilter("") }}
            >
              Clear filters
            </button>
          )}
          <span className="ml-auto text-xs text-neutral-400">{ecns.length} result{ecns.length !== 1 ? "s" : ""}</span>
        </div>

        {/* Table */}
        {isLoading && (
          <div className="flex items-center justify-center py-20">
            <Spinner size="lg" />
          </div>
        )}
        {isError && (
          <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            Failed to load ECNs — check that the backend is running.
          </div>
        )}
        {!isLoading && !isError && (
          <div className="rounded-lg border bg-white overflow-hidden shadow-sm">
            <Table>
              <TableHeader>
                <TableRow className="bg-neutral-50 hover:bg-neutral-50">
                  <TableHead className="w-36 font-medium text-xs uppercase tracking-wide text-neutral-500">Number</TableHead>
                  <TableHead className="font-medium text-xs uppercase tracking-wide text-neutral-500">Title</TableHead>
                  <TableHead className="w-36 font-medium text-xs uppercase tracking-wide text-neutral-500">Status</TableHead>
                  <TableHead className="w-28 font-medium text-xs uppercase tracking-wide text-neutral-500 hidden md:table-cell">Originator</TableHead>
                  <TableHead className="w-32 font-medium text-xs uppercase tracking-wide text-neutral-500 hidden lg:table-cell">Next action</TableHead>
                  <TableHead className="w-20 text-right font-medium text-xs uppercase tracking-wide text-neutral-500">Age</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {ecns.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-16">
                      <p className="text-sm text-neutral-400">
                        {search || statusFilter ? "No ECNs match your filters." : "No ECNs yet — create the first one."}
                      </p>
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
                      className={`cursor-pointer transition-colors duration-[150ms] ${
                        isMyAction ? "bg-blue-50/40 hover:bg-blue-50" : "hover:bg-neutral-50"
                      }`}
                      onClick={() => navigate(`/ecn/${ecn.id}`)}
                    >
                      <TableCell>
                        <Link
                          to={`/ecn/${ecn.id}`}
                          onClick={(e) => e.stopPropagation()}
                          className="font-mono text-sm font-medium text-neutral-800 hover:text-neutral-900 hover:underline"
                        >
                          {ecn.ecn_number}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <span className="text-sm text-neutral-800 line-clamp-1">{ecn.title}</span>
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusBadgeVariant(ecn.status)}>
                          {statusLabel(ecn.status)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-neutral-500 hidden md:table-cell">
                        {ecn.originator_username}
                      </TableCell>
                      <TableCell className="hidden lg:table-cell">
                        {ecn.next_action_users?.length > 0 ? (
                          <span className="text-xs text-neutral-600 font-medium">
                            {ecn.next_action_users.join(", ")}
                          </span>
                        ) : (
                          <span className="text-xs text-neutral-300">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <span className={`text-xs tabular-nums font-mono ${isOverdue ? "text-red-500 font-semibold" : "text-neutral-400"}`}>
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

const STAT_COLOR_STYLES: Record<StatColor, string> = {
  default: "border-neutral-200 bg-white",
  info:    "border-blue-200 bg-blue-50",
  warning: "border-orange-200 bg-orange-50",
  success: "border-green-200 bg-green-50",
  error:   "border-red-200 bg-red-50",
}

const STAT_VALUE_STYLES: Record<StatColor, string> = {
  default: "text-neutral-800",
  info:    "text-blue-700",
  warning: "text-orange-600",
  success: "text-green-700",
  error:   "text-red-600",
}

function StatCard({ label, value, color = "default" }: StatCardProps) {
  return (
    <div className={`rounded-lg border px-4 py-3 shadow-sm hover:shadow-md transition-shadow duration-[200ms] ${STAT_COLOR_STYLES[color]}`}>
      <p className="text-xs font-medium uppercase tracking-wider text-neutral-500 mb-1">{label}</p>
      <p className={`text-2xl font-bold tabular-nums ${STAT_VALUE_STYLES[color]}`}>{value}</p>
    </div>
  )
}
