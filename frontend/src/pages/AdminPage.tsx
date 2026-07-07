import { useState } from "react"
import { Link } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Spinner } from "@/components/ui/spinner"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useAuthStore } from "@/store/auth"
import axiosInstance from "@/api/axios"
import { ROLE_LABEL } from "@/lib/ecn-workflow"

// ── Types ──────────────────────────────────────────────────────────────────────

interface RoleUser {
  id: string
  facility: string
  role_id: string
  username: string
  display_name: string | null
  email: string | null
  notes: string | null
  is_active: boolean
  added_by: string | null
  added_at: string | null
}

// ── API ────────────────────────────────────────────────────────────────────────

async function fetchRoleUsers(): Promise<RoleUser[]> {
  const { data } = await axiosInstance.get("/api/v1/admin/roles")
  return data
}

async function addRoleUser(body: {
  facility: string; role_id: string; username: string
  display_name?: string; email?: string; notes?: string
}): Promise<RoleUser> {
  const { data } = await axiosInstance.post("/api/v1/admin/roles", body)
  return data
}

async function removeRoleUser(id: string): Promise<void> {
  await axiosInstance.delete(`/api/v1/admin/roles/${id}`)
}

// ── Role constants ─────────────────────────────────────────────────────────────

const VALID_ROLE_IDS = [
  "DC", "OR", "SE", "CE", "EM", "QM", "PM", "SC", "FN", "AD", "CA", "RD", "TE", "MQ",
]

// ── Sub-components ─────────────────────────────────────────────────────────────

function AddRoleUserForm({ onSuccess }: { onSuccess: () => void }) {
  const [facility, setFacility] = useState("D")
  const [roleId, setRoleId]     = useState("SE")
  const [username, setUsername] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [email, setEmail]       = useState("")
  const [error, setError]       = useState<string | null>(null)

  const mut = useMutation({
    mutationFn: () => addRoleUser({
      facility, role_id: roleId, username: username.trim(),
      display_name: displayName.trim() || undefined,
      email: email.trim() || undefined,
    }),
    onSuccess: () => {
      setUsername(""); setDisplayName(""); setEmail(""); setError(null)
      onSuccess()
    },
    onError: (err: any) => {
      setError(err?.response?.data?.detail ?? "Failed to add user")
    },
  })

  return (
    <div className="border border-[#e2e8f0] rounded-lg p-4 bg-[#f8fafc] space-y-3">
      <p className="text-sm font-medium text-[#1e293b]">Add role assignment</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="space-y-1">
          <label className="text-xs text-[#64748b]">Facility</label>
          <input
            className="w-full border border-[#e2e8f0] rounded px-2 py-1.5 text-sm"
            value={facility} onChange={(e) => setFacility(e.target.value)} placeholder="D"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-[#64748b]">Role</label>
          <select
            className="w-full border border-[#e2e8f0] rounded px-2 py-1.5 text-sm bg-white"
            value={roleId} onChange={(e) => setRoleId(e.target.value)}
          >
            {VALID_ROLE_IDS.map((r) => (
              <option key={r} value={r}>{r} — {ROLE_LABEL[r] ?? r}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-[#64748b]">Username *</label>
          <input
            className="w-full border border-[#e2e8f0] rounded px-2 py-1.5 text-sm"
            value={username} onChange={(e) => setUsername(e.target.value)} placeholder="jsmith"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-[#64748b]">Display name</label>
          <input
            className="w-full border border-[#e2e8f0] rounded px-2 py-1.5 text-sm"
            value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="John Smith"
          />
        </div>
      </div>
      <div className="flex items-center gap-3">
        <input
          className="flex-1 border border-[#e2e8f0] rounded px-2 py-1.5 text-sm"
          value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email (optional)"
        />
        <Button
          size="sm"
          disabled={!username.trim() || mut.isPending}
          onClick={() => mut.mutate()}
        >
          {mut.isPending ? <Spinner size="sm" /> : "Add"}
        </Button>
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  )
}

function RoleUsersTab() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [filterRole, setFilterRole] = useState("")

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["admin-roles"],
    queryFn: fetchRoleUsers,
    staleTime: 0,
  })

  const remove = useMutation({
    mutationFn: removeRoleUser,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-roles"] }),
  })

  const filtered = filterRole ? users.filter((u) => u.role_id === filterRole) : users
  const grouped = VALID_ROLE_IDS.reduce<Record<string, RoleUser[]>>((acc, r) => {
    const rows = filtered.filter((u) => u.role_id === r)
    if (rows.length) acc[r] = rows
    return acc
  }, {})

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <select
            className="border border-[#e2e8f0] rounded px-2 py-1.5 text-sm bg-white"
            value={filterRole} onChange={(e) => setFilterRole(e.target.value)}
          >
            <option value="">All roles</option>
            {VALID_ROLE_IDS.map((r) => (
              <option key={r} value={r}>{r} — {ROLE_LABEL[r] ?? r}</option>
            ))}
          </select>
          {isLoading && <Spinner size="sm" />}
        </div>
        <Button size="sm" variant="outline" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Cancel" : "+ Add"}
        </Button>
      </div>

      {showForm && (
        <AddRoleUserForm onSuccess={() => {
          qc.invalidateQueries({ queryKey: ["admin-roles"] })
          setShowForm(false)
        }} />
      )}

      {Object.keys(grouped).length === 0 && !isLoading && (
        <p className="text-sm text-[#94a3b8] text-center py-8">No role assignments found.</p>
      )}

      {Object.entries(grouped).map(([roleId, rows]) => (
        <div key={roleId} className="border border-[#e2e8f0] rounded-lg overflow-hidden">
          <div className="bg-[#f1f5f9] px-4 py-2 flex items-center gap-2">
            <span className="font-mono text-xs font-bold text-[#0066cc]">{roleId}</span>
            <span className="text-sm text-[#475569]">{ROLE_LABEL[roleId] ?? roleId}</span>
            <Badge variant="secondary" className="ml-auto text-xs">{rows.length}</Badge>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Username</TableHead>
                <TableHead>Display name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Facility</TableHead>
                <TableHead>Added by</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((u) => (
                <TableRow key={u.id} className={u.is_active ? "" : "opacity-40"}>
                  <TableCell className="font-mono text-sm">{u.username}</TableCell>
                  <TableCell className="text-sm">{u.display_name ?? "—"}</TableCell>
                  <TableCell className="text-sm text-[#64748b]">{u.email ?? "—"}</TableCell>
                  <TableCell className="text-sm">{u.facility}</TableCell>
                  <TableCell className="text-sm text-[#94a3b8]">{u.added_by ?? "—"}</TableCell>
                  <TableCell className="text-right">
                    <Button
                      size="sm"
                      variant="destructive"
                      disabled={remove.isPending}
                      onClick={() => {
                        if (window.confirm(`Remove ${u.username} from ${roleId}?`))
                          remove.mutate(u.id)
                      }}
                    >
                      Remove
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ))}
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function AdminPage() {
  const user = useAuthStore((s) => s.user)

  const isDC = user?.groups?.includes("OSKAR-DC") ?? false

  if (!isDC) {
    return (
      <div className="min-h-screen bg-[#f5f7fa] flex items-center justify-center">
        <div className="text-center space-y-2">
          <p className="text-lg font-semibold text-[#1e293b]">Access denied</p>
          <p className="text-sm text-[#64748b]">Admin area is restricted to Document Controllers.</p>
          <Link to="/ecn" className="text-sm text-[#0066cc] hover:underline">← Back to ECNs</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#f5f7fa] flex flex-col">
      <header className="sticky top-0 z-[1020] border-b border-[#e8ecf0] bg-white px-6 h-14 flex items-center justify-between shadow-[var(--shadow-xs)]">
        <div className="flex items-center gap-3">
          <Link to="/ecn" className="text-sm text-[#94a3b8] hover:text-[#475569] transition-colors">
            ← ECNs
          </Link>
          <span className="text-[#e2e8f0]">|</span>
          <span className="font-semibold text-sm text-[#1e293b]">Administration</span>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-5xl px-6 py-6">
        <RoleUsersTab />
      </main>
    </div>
  )
}
