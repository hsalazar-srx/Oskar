import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useAuthStore } from "@/store/auth"
import axiosInstance from "@/api/axios"

const STATUS_LABELS: Record<number, string> = {
  0: "Draft",
  5: "Engineering Review",
  10: "Management Review",
  20: "DC Review",
  25: "DC Approved",
  30: "Implemented",
  40: "Closed",
  50: "On Hold",
  60: "Rejected",
  70: "Abandoned",
}

const STATUS_VARIANT: Record<number, "default" | "secondary" | "destructive" | "outline"> = {
  0: "outline",
  5: "secondary",
  10: "secondary",
  20: "default",
  25: "default",
  30: "default",
  40: "outline",
  50: "secondary",
  60: "destructive",
  70: "destructive",
}

function statusLabel(s: number) { return STATUS_LABELS[s] ?? `Status ${s}` }
function statusVariant(s: number) { return STATUS_VARIANT[s] ?? "outline" }

function ageDays(createdAt: string) {
  return Math.floor((Date.now() - new Date(createdAt).getTime()) / 86_400_000)
}

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

export default function ECNListPage() {
  const navigate = useNavigate()
  const logout = useAuthStore((s) => s.logout)
  const [statusFilter, setStatusFilter] = useState("")
  const [search, setSearch] = useState("")

  const params: Record<string, string> = {}
  if (statusFilter) params.status = statusFilter
  if (search) params.search = search

  const { data: ecns = [], isLoading, isError } = useQuery({
    queryKey: ["ecns", params],
    queryFn: () => fetchECNs(params),
  })

  return (
    <div className="min-h-screen bg-neutral-50">
      {/* Header */}
      <header className="border-b bg-white px-6 py-3 flex items-center justify-between">
        <span className="font-semibold tracking-tight">Oskar <span className="text-neutral-400 font-normal text-sm">/ ECN</span></span>
        <div className="flex items-center gap-3">
          <Button size="sm" onClick={() => navigate("/ecn/new")}>+ New ECN</Button>
          <Button size="sm" variant="ghost" onClick={logout}>Sign out</Button>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-6 space-y-4">
        {/* Filters */}
        <div className="flex gap-3">
          <Input
            placeholder="Search title or number…"
            className="max-w-xs"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            className="rounded-md border border-neutral-200 bg-white px-3 py-1.5 text-sm"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All statuses</option>
            {Object.entries(STATUS_LABELS).map(([v, label]) => (
              <option key={v} value={v}>{label}</option>
            ))}
          </select>
        </div>

        {/* Table */}
        {isLoading && <p className="text-sm text-neutral-400">Loading…</p>}
        {isError && <p className="text-sm text-red-500">Failed to load ECNs.</p>}
        {!isLoading && !isError && (
          <div className="rounded-lg border bg-white overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-36">Number</TableHead>
                  <TableHead>Title</TableHead>
                  <TableHead className="w-32">Status</TableHead>
                  <TableHead className="w-28">Next action</TableHead>
                  <TableHead className="w-20 text-right">Age</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {ecns.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="text-center text-neutral-400 py-10">
                      No ECNs found
                    </TableCell>
                  </TableRow>
                )}
                {ecns.map((ecn) => (
                  <TableRow key={ecn.id} className="cursor-pointer hover:bg-neutral-50">
                    <TableCell>
                      <Link to={`/ecn/${ecn.id}`} className="font-mono text-sm hover:underline">
                        {ecn.ecn_number}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Link to={`/ecn/${ecn.id}`} className="hover:underline">
                        {ecn.title}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Badge variant={statusVariant(ecn.status)}>
                        {statusLabel(ecn.status)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-neutral-500">
                      {ecn.next_action_users?.join(", ") ?? "—"}
                    </TableCell>
                    <TableCell className="text-right text-sm text-neutral-400">
                      {ageDays(ecn.created_at)}d
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </main>
    </div>
  )
}
