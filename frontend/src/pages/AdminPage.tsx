import { useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { Spinner } from "@/components/ui/spinner"
import { Button } from "@/components/ui/button"
import { useAuthStore } from "@/store/auth"
import axiosInstance from "@/api/axios"
import { ROLE_LABEL } from "@/lib/ecn-workflow"
import {
  fetchCustomers,
  fetchCustomerRoleDefaults,
  addCustomerRoleDefault,
  setCustomerRoleDefault,
  removeCustomerRoleDefault,
  fetchMovexOutbox,
  retryMovexOutboxEntry,
  type CustomerEntry,
  type CustomerRoleDefault,
  type MovexOutboxEntry,
} from "@/api/ecn"

// ── Types ──────────────────────────────────────────────────────────────────────

interface LdapMember {
  username: string
  display_name: string | null
  email: string | null
}

interface LdapGroup {
  cn: string
  distinguished_name: string
  members: LdapMember[]
}

interface RoleUser {
  id: string
  facility: string
  role_id: string
  username: string
  display_name: string | null
  email: string | null
  is_active: boolean
  added_by: string | null
}

// ── API ────────────────────────────────────────────────────────────────────────

async function fetchLdapGroups(): Promise<LdapGroup[]> {
  const { data } = await axiosInstance.get("/api/v1/admin/ldap-groups")
  return data
}

async function fetchRoleUsers(): Promise<RoleUser[]> {
  const { data } = await axiosInstance.get("/api/v1/admin/roles")
  return data
}

async function addRoleUser(body: {
  role_id: string
  username: string
  facility: string
  display_name?: string
  email?: string
}): Promise<RoleUser> {
  const { data } = await axiosInstance.post("/api/v1/admin/roles", body)
  return data
}

async function removeRoleUser(id: string): Promise<void> {
  await axiosInstance.delete(`/api/v1/admin/roles/${id}`)
}

// ── Helpers ────────────────────────────────────────────────────────────────────

const VALID_ROLE_IDS = [
  "DC", "OR", "SE", "CE", "EM", "QM", "PM", "SC", "FN", "AD", "CA", "RD", "TE", "MQ",
]

const FACILITY_OPTIONS = [
  { value: "D", label: "D — Melbourne" },
  { value: "L", label: "L — Johor Bahru" },
]

function groupPrefix(cn: string): string {
  const m = cn.match(/^([a-z]+)-/)
  return m ? m[1].toUpperCase() : "OTHER"
}

const APP_PREFIX_LABEL: Record<string, string> = {
  ECN: "Engineering Change Note",
  MES: "Manufacturing Execution System",
  PUR: "Purchasing",
}

// ── LDAP Groups section ───────────────────────────────────────────────────────

function LdapGroupsSection() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-ldap-groups"],
    queryFn: fetchLdapGroups,
    staleTime: 60_000,
  })

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-[#94a3b8]">
        <Spinner size="sm" /> Querying Active Directory…
      </div>
    )
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
        Failed to load LDAP groups. Check LDAP connectivity or service account permissions.
      </div>
    )
  }

  if (!data || data.length === 0) {
    return (
      <p className="text-sm text-[#94a3b8] py-8 text-center">
        No Application Role groups found in Active Directory, or running in dev mode (LDAP not active).
      </p>
    )
  }

  // Group by prefix (ecn- / mes- / pur-)
  const byPrefix: Record<string, LdapGroup[]> = {}
  for (const g of data) {
    const prefix = groupPrefix(g.cn)
    ;(byPrefix[prefix] ??= []).push(g)
  }

  return (
    <div className="space-y-5">
      {Object.entries(byPrefix).map(([prefix, groups]) => (
        <div key={prefix}>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-[#94a3b8]">
              {APP_PREFIX_LABEL[prefix] ?? prefix}
            </span>
            <span className="text-[10px] font-mono text-[#cbd5e1]">{prefix.toLowerCase()}-*</span>
          </div>
          <div className="space-y-2">
            {groups.map((group) => (
              <div key={group.cn} className="rounded-lg border border-[#e8ecf0] overflow-hidden">
                <div className="flex items-center justify-between px-4 py-2.5 bg-[#f8fafc] border-b border-[#f1f5f9]">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-semibold text-[#0066cc]">{group.cn}</span>
                  </div>
                  <Badge variant="secondary" className="text-[11px]">
                    {group.members.length} member{group.members.length !== 1 ? "s" : ""}
                  </Badge>
                </div>

                {group.members.length === 0 ? (
                  <p className="px-4 py-3 text-xs text-[#94a3b8] italic">No members</p>
                ) : (
                  <div className="divide-y divide-[#f8fafc]">
                    {group.members.map((m) => (
                      <div key={m.username} className="flex items-center gap-3 px-4 py-2.5">
                        <div className="w-7 h-7 rounded-full bg-[#eff6ff] flex items-center justify-center shrink-0">
                          <span className="text-[11px] font-bold text-[#0066cc]">
                            {(m.display_name ?? m.username).charAt(0).toUpperCase()}
                          </span>
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-[#0f172a] truncate">
                            {m.display_name ?? m.username}
                          </p>
                          <p className="text-[11px] text-[#94a3b8] font-mono">{m.username}</p>
                        </div>
                        {m.email && (
                          <span className="ml-auto text-xs text-[#94a3b8] truncate hidden sm:block">
                            {m.email}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Add role user inline form ─────────────────────────────────────────────────

interface AddRoleFormProps {
  roleId: string
  onClose: () => void
}

function AddRoleForm({ roleId, onClose }: AddRoleFormProps) {
  const qc = useQueryClient()
  const [username, setUsername] = useState("")
  const [facility, setFacility] = useState("D")
  const [error, setError] = useState<string | null>(null)

  const add = useMutation({
    mutationFn: addRoleUser,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-roles"] })
      onClose()
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? "Failed to add user.")
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!username.trim()) return
    setError(null)
    add.mutate({ role_id: roleId, username: username.trim(), facility })
  }

  return (
    <form onSubmit={handleSubmit} className="px-4 py-3 bg-[#eff6ff] border-t border-blue-100">
      <div className="flex items-center gap-2 flex-wrap">
        <input
          autoFocus
          type="text"
          placeholder="AD username (e.g. jsmith)"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="h-8 flex-1 min-w-[160px] rounded border border-[#d1d9e0] bg-white px-2.5 text-sm text-[#0f172a] placeholder:text-[#94a3b8] focus:outline-none focus:border-[#0066cc] focus:ring-1 focus:ring-[#0066cc]/20"
        />
        <select
          value={facility}
          onChange={(e) => setFacility(e.target.value)}
          className="h-8 rounded border border-[#d1d9e0] bg-white px-2 text-sm text-[#475569] focus:outline-none focus:border-[#0066cc] focus:ring-1 focus:ring-[#0066cc]/20"
        >
          {FACILITY_OPTIONS.map((f) => (
            <option key={f.value} value={f.value}>{f.label}</option>
          ))}
        </select>
        <Button type="submit" size="sm" disabled={add.isPending || !username.trim()}>
          {add.isPending ? "…" : "Add"}
        </Button>
        <button
          type="button"
          onClick={onClose}
          className="text-xs text-[#94a3b8] hover:text-[#475569] transition-colors px-1"
        >
          Cancel
        </button>
      </div>
      {error && <p className="text-xs text-red-600 mt-1.5">{error}</p>}
    </form>
  )
}

// ── ECN Role Assignments section ──────────────────────────────────────────────

function RoleAssignmentsSection() {
  const qc = useQueryClient()
  const [addingRole, setAddingRole] = useState<string | null>(null)
  const [confirmRemove, setConfirmRemove] = useState<RoleUser | null>(null)

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["admin-roles"],
    queryFn: fetchRoleUsers,
    staleTime: 0,
  })

  const remove = useMutation({
    mutationFn: removeRoleUser,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-roles"] })
      setConfirmRemove(null)
    },
  })

  // Show all valid roles, not just those with users (so empty roles are still visible with an Add button)
  const grouped = VALID_ROLE_IDS.reduce<Record<string, RoleUser[]>>((acc, r) => {
    acc[r] = users.filter((u) => u.role_id === r && u.is_active)
    return acc
  }, {})

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-[#94a3b8]">
        <Spinner size="sm" /> Loading role assignments…
      </div>
    )
  }

  return (
    <>
      <div className="space-y-2">
        {Object.entries(grouped).map(([roleId, rows]) => (
          <div key={roleId} className="rounded-lg border border-[#e8ecf0] overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-2.5 bg-[#f8fafc] border-b border-[#f1f5f9]">
              <span className="font-mono text-xs font-bold text-[#0066cc]">{roleId}</span>
              <span className="text-sm text-[#475569]">{ROLE_LABEL[roleId] ?? roleId}</span>
              <Badge variant="secondary" className="ml-auto text-[11px]">
                {rows.length}
              </Badge>
              <button
                type="button"
                onClick={() => setAddingRole(addingRole === roleId ? null : roleId)}
                className={`ml-1 text-[11px] font-semibold px-2 py-0.5 rounded transition-colors duration-150 ${
                  addingRole === roleId
                    ? "bg-blue-100 text-[#0066cc]"
                    : "text-[#94a3b8] hover:text-[#0066cc] hover:bg-blue-50"
                }`}
              >
                + Add
              </button>
            </div>

            {rows.length === 0 && addingRole !== roleId && (
              <p className="px-4 py-2.5 text-xs text-[#cbd5e1] italic">No users assigned</p>
            )}

            {rows.length > 0 && (
              <div className="divide-y divide-[#f8fafc]">
                {rows.map((u) => (
                  <div key={u.id} className="flex items-center gap-3 px-4 py-2.5 group">
                    <div className="w-7 h-7 rounded-full bg-[#f0fdf4] flex items-center justify-center shrink-0">
                      <span className="text-[11px] font-bold text-emerald-600">
                        {(u.display_name ?? u.username).charAt(0).toUpperCase()}
                      </span>
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-[#0f172a] truncate">
                        {u.display_name ?? u.username}
                      </p>
                      <p className="text-[11px] text-[#94a3b8] font-mono">{u.username}</p>
                    </div>
                    <div className="ml-auto flex items-center gap-3 shrink-0">
                      <span className="text-[11px] text-[#94a3b8]">
                        Facility: <strong className="text-[#475569]">{u.facility}</strong>
                      </span>
                      {u.email && (
                        <span className="text-xs text-[#94a3b8] hidden sm:block">{u.email}</span>
                      )}
                      <button
                        type="button"
                        onClick={() => setConfirmRemove(u)}
                        title="Remove this user from role"
                        className="opacity-0 group-hover:opacity-100 text-[#94a3b8] hover:text-red-500 transition-all duration-150 p-0.5"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {addingRole === roleId && (
              <AddRoleForm roleId={roleId} onClose={() => setAddingRole(null)} />
            )}
          </div>
        ))}
      </div>

      {/* Remove confirmation modal */}
      {confirmRemove && (
        <div
          className="fixed inset-0 z-[1080] flex items-center justify-center bg-black/40"
          onMouseDown={(e) => { if (e.target === e.currentTarget) setConfirmRemove(null) }}
        >
          <div className="w-full max-w-sm rounded-lg bg-white shadow-xl mx-4 p-5 space-y-4">
            <div>
              <h3 className="text-base font-semibold text-[#0f172a]">Remove role assignment?</h3>
              <p className="text-sm text-[#475569] mt-1">
                Remove <strong>{confirmRemove.display_name ?? confirmRemove.username}</strong> from{" "}
                <strong>{ROLE_LABEL[confirmRemove.role_id] ?? confirmRemove.role_id}</strong>{" "}
                (Facility {confirmRemove.facility})?
              </p>
              <p className="text-xs text-[#94a3b8] mt-1">
                This only removes the default assignment — existing ECN role assignments are not affected.
              </p>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setConfirmRemove(null)}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                size="sm"
                disabled={remove.isPending}
                onClick={() => remove.mutate(confirmRemove.id)}
              >
                {remove.isPending ? "…" : "Remove"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

// ── Customer role defaults (SE/PM per customer) ───────────────────────────────

function AddCustomerRoleForm({
  cuno,
  roleId,
  onClose,
}: {
  cuno: string
  roleId: "SE" | "PM"
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [username, setUsername] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [error, setError] = useState<string | null>(null)

  const add = useMutation({
    mutationFn: addCustomerRoleDefault,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-customer-role-defaults"] })
      onClose()
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? "Failed to add candidate.")
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!username.trim()) return
    setError(null)
    add.mutate({
      cuno,
      role_id: roleId,
      username: username.trim(),
      display_name: displayName.trim() || undefined,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="px-4 py-3 bg-[#eff6ff] border-t border-blue-100">
      <div className="flex items-center gap-2 flex-wrap">
        <input
          autoFocus
          type="text"
          placeholder="AD username (e.g. jsmith)"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="h-8 flex-1 min-w-[140px] rounded border border-[#d1d9e0] bg-white px-2.5 text-sm text-[#0f172a] placeholder:text-[#94a3b8] focus:outline-none focus:border-[#0066cc] focus:ring-1 focus:ring-[#0066cc]/20"
        />
        <input
          type="text"
          placeholder="Display name (optional)"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          className="h-8 flex-1 min-w-[140px] rounded border border-[#d1d9e0] bg-white px-2.5 text-sm text-[#0f172a] placeholder:text-[#94a3b8] focus:outline-none focus:border-[#0066cc] focus:ring-1 focus:ring-[#0066cc]/20"
        />
        <Button type="submit" size="sm" disabled={add.isPending || !username.trim()}>
          {add.isPending ? "…" : "Add"}
        </Button>
        <button
          type="button"
          onClick={onClose}
          className="text-xs text-[#94a3b8] hover:text-[#475569] transition-colors px-1"
        >
          Cancel
        </button>
      </div>
      {error && <p className="text-xs text-red-600 mt-1.5">{error}</p>}
    </form>
  )
}

function CustomerRoleDefaultsSection() {
  const qc = useQueryClient()
  const [search, setSearch] = useState("")
  const [selectedCuno, setSelectedCuno] = useState<string | null>(null)
  const [addingRole, setAddingRole] = useState<"SE" | "PM" | null>(null)

  const { data: customers = [] } = useQuery({
    queryKey: ["customers"],
    queryFn: fetchCustomers,
    staleTime: 5 * 60_000,
  })

  const { data: defaults = [], isLoading } = useQuery({
    queryKey: ["admin-customer-role-defaults"],
    queryFn: () => fetchCustomerRoleDefaults(),
    staleTime: 0,
  })

  const setDefault = useMutation({
    mutationFn: ({ id, cuno, roleId }: { id: string; cuno: string; roleId: string }) =>
      setCustomerRoleDefault(id, cuno, roleId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-customer-role-defaults"] }),
  })

  const remove = useMutation({
    mutationFn: removeCustomerRoleDefault,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-customer-role-defaults"] }),
  })

  // Customers that have at least one candidate row, grouped by cuno
  const byCuno = useMemo(() => {
    const map: Record<string, CustomerRoleDefault[]> = {}
    for (const d of defaults) {
      if (!d.is_active) continue
      ;(map[d.cuno] ??= []).push(d)
    }
    return map
  }, [defaults])

  const customerList: (CustomerEntry & { hasDefaults: boolean })[] = useMemo(() => {
    const known = customers.map((c) => ({ ...c, hasDefaults: Boolean(byCuno[c.cuno]) }))
    const q = search.trim().toLowerCase()
    if (!q) return known
    return known.filter(
      (c) => c.cuno.toLowerCase().includes(q) || (c.name ?? "").toLowerCase().includes(q),
    )
  }, [customers, byCuno, search])

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-[#94a3b8]">
        <Spinner size="sm" /> Loading customer role defaults…
      </div>
    )
  }

  const selectedCandidates = selectedCuno ? byCuno[selectedCuno] ?? [] : []

  return (
    <div className="grid grid-cols-1 md:grid-cols-[220px_1fr] gap-4">
      {/* Customer picker */}
      <div className="space-y-2">
        <input
          type="text"
          placeholder="Search customer / CUNO…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-8 w-full rounded border border-[#d1d9e0] bg-white px-2.5 text-sm text-[#0f172a] placeholder:text-[#94a3b8] focus:outline-none focus:border-[#0066cc] focus:ring-1 focus:ring-[#0066cc]/20"
        />
        <div className="max-h-96 overflow-y-auto rounded-lg border border-[#e8ecf0] divide-y divide-[#f8fafc]">
          {customerList.map((c) => (
            <button
              key={c.cuno}
              type="button"
              onClick={() => setSelectedCuno(c.cuno)}
              className={`w-full text-left px-3 py-2 text-xs transition-colors duration-100 ${
                selectedCuno === c.cuno ? "bg-[#eff6ff] text-[#0066cc]" : "hover:bg-[#f8fafc] text-[#475569]"
              }`}
            >
              <div className="flex items-center gap-1.5">
                <span className="font-mono text-[10px] text-[#94a3b8]">{c.cuno}</span>
                {c.hasDefaults && <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />}
              </div>
              <p className="truncate">{c.name ?? "—"}</p>
            </button>
          ))}
          {customerList.length === 0 && (
            <p className="px-3 py-4 text-xs text-[#94a3b8] text-center">No customers match.</p>
          )}
        </div>
      </div>

      {/* Candidates for selected customer */}
      <div>
        {!selectedCuno ? (
          <p className="text-sm text-[#94a3b8] py-8 text-center">
            Select a customer to view or manage SE / PM candidates.
          </p>
        ) : (
          <div className="space-y-3">
            {(["SE", "PM"] as const).map((roleId) => {
              const rows = selectedCandidates.filter((d) => d.role_id === roleId)
              return (
                <div key={roleId} className="rounded-lg border border-[#e8ecf0] overflow-hidden">
                  <div className="flex items-center gap-2 px-4 py-2.5 bg-[#f8fafc] border-b border-[#f1f5f9]">
                    <span className="font-mono text-xs font-bold text-[#0066cc]">{roleId}</span>
                    <span className="text-sm text-[#475569]">{ROLE_LABEL[roleId] ?? roleId}</span>
                    <Badge variant="secondary" className="ml-auto text-[11px]">{rows.length}</Badge>
                    <button
                      type="button"
                      onClick={() => setAddingRole(addingRole === roleId ? null : roleId)}
                      className={`ml-1 text-[11px] font-semibold px-2 py-0.5 rounded transition-colors duration-150 ${
                        addingRole === roleId
                          ? "bg-blue-100 text-[#0066cc]"
                          : "text-[#94a3b8] hover:text-[#0066cc] hover:bg-blue-50"
                      }`}
                    >
                      + Add
                    </button>
                  </div>

                  {rows.length === 0 && addingRole !== roleId && (
                    <p className="px-4 py-2.5 text-xs text-[#cbd5e1] italic">No candidates on file</p>
                  )}

                  {rows.length > 0 && (
                    <div className="divide-y divide-[#f8fafc]">
                      {rows.map((r) => (
                        <div key={r.id} className="flex items-center gap-3 px-4 py-2.5 group">
                          <div className="w-7 h-7 rounded-full bg-[#f0fdf4] flex items-center justify-center shrink-0">
                            <span className="text-[11px] font-bold text-emerald-600">
                              {(r.display_name ?? r.username).charAt(0).toUpperCase()}
                            </span>
                          </div>
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-[#0f172a] truncate">
                              {r.display_name ?? r.username}
                            </p>
                            <p className="text-[11px] text-[#94a3b8] font-mono">{r.username}</p>
                          </div>
                          <div className="ml-auto flex items-center gap-2 shrink-0">
                            {r.source === "stargile_import" && (
                              <span className="text-[10px] text-[#94a3b8] italic">imported</span>
                            )}
                            {r.is_default ? (
                              <Badge className="text-[10px] bg-emerald-100 text-emerald-700 hover:bg-emerald-100">
                                Default
                              </Badge>
                            ) : (
                              <button
                                type="button"
                                onClick={() => setDefault.mutate({ id: r.id, cuno: selectedCuno, roleId })}
                                disabled={setDefault.isPending}
                                className="text-[11px] text-[#94a3b8] hover:text-[#0066cc] px-1.5 py-0.5 rounded hover:bg-blue-50 transition-colors duration-100"
                              >
                                Make default
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => remove.mutate(r.id)}
                              title="Remove candidate"
                              className="opacity-0 group-hover:opacity-100 text-[#94a3b8] hover:text-red-500 transition-all duration-150 p-0.5"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                              </svg>
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {addingRole === roleId && (
                    <AddCustomerRoleForm
                      cuno={selectedCuno}
                      roleId={roleId}
                      onClose={() => setAddingRole(null)}
                    />
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Movex outbox recovery (S9-4) ────────────────────────────────────────────────

const OUTBOX_STATE_BADGE: Record<string, string> = {
  failed: "bg-amber-100 text-amber-700 hover:bg-amber-100",
  abandoned: "bg-red-100 text-red-700 hover:bg-red-100",
}

function relativeTimeShort(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(ms / 60_000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

function MovexOutboxSection() {
  const qc = useQueryClient()
  const [stateFilter, setStateFilter] = useState<string>("")
  const [confirmRetry, setConfirmRetry] = useState<MovexOutboxEntry | null>(null)

  const { data: entries = [], isLoading, isFetching } = useQuery({
    queryKey: ["admin-movex-outbox", stateFilter],
    queryFn: () => fetchMovexOutbox(stateFilter ? { state: stateFilter } : undefined),
    staleTime: 0,
    refetchInterval: 30_000,
  })

  const retry = useMutation({
    mutationFn: (id: string) => retryMovexOutboxEntry(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-movex-outbox"] })
      setConfirmRetry(null)
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-[#94a3b8]">
        <Spinner size="sm" /> Loading failed Movex writes…
      </div>
    )
  }

  return (
    <>
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <select
            value={stateFilter}
            onChange={(e) => setStateFilter(e.target.value)}
            className="h-8 rounded border border-[#d1d9e0] bg-white px-2 text-xs text-[#475569] focus:outline-none focus:border-[#0066cc] focus:ring-1 focus:ring-[#0066cc]/20"
          >
            <option value="">Failed + Abandoned (default)</option>
            <option value="failed">Failed only</option>
            <option value="abandoned">Abandoned only</option>
            <option value="pending">Pending</option>
            <option value="processing">Processing</option>
            <option value="completed">Completed</option>
          </select>
          {isFetching && <Spinner size="sm" />}
          <span className="ml-auto text-[11px] text-[#94a3b8]">Auto-refreshes every 30s</span>
        </div>

        {entries.length === 0 ? (
          <p className="text-sm text-[#94a3b8] py-8 text-center">
            No {stateFilter || "failed or abandoned"} Movex writes — everything is up to date.
          </p>
        ) : (
          <div className="rounded-lg border border-[#e8ecf0] divide-y divide-[#f8fafc] overflow-hidden">
            {entries.map((entry) => (
              <div key={entry.id} className="px-4 py-3 flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-xs font-bold text-[#0066cc]">{entry.ecn_number}</span>
                    <span className="text-xs text-[#475569]">{entry.mi_transaction}</span>
                    <Badge className={`text-[10px] ${OUTBOX_STATE_BADGE[entry.state] ?? "bg-neutral-100 text-neutral-600"}`}>
                      {entry.state}
                    </Badge>
                    <span className="text-[11px] text-[#94a3b8]">
                      Facility {entry.facility} · attempt {entry.attempt_count}/{entry.max_attempts}
                    </span>
                  </div>
                  {entry.last_error && (
                    <p className="mt-1 text-xs text-red-600 truncate" title={entry.last_error}>
                      {entry.last_error}
                    </p>
                  )}
                  <div className="mt-1 flex items-center gap-3 text-[11px] text-[#94a3b8]">
                    <span>Updated {relativeTimeShort(entry.updated_at)}</span>
                    {entry.next_retry_at && entry.state === "failed" && (
                      <span>Next auto-retry {relativeTimeShort(entry.next_retry_at)}</span>
                    )}
                  </div>
                </div>
                {(entry.state === "failed" || entry.state === "abandoned") && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs shrink-0"
                    onClick={() => setConfirmRetry(entry)}
                  >
                    Retry now
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {confirmRetry && (
        <div
          className="fixed inset-0 z-[1080] flex items-center justify-center bg-black/40"
          onMouseDown={(e) => { if (e.target === e.currentTarget) setConfirmRetry(null) }}
        >
          <div className="w-full max-w-sm rounded-lg bg-white shadow-xl mx-4 p-5 space-y-4">
            <div>
              <h3 className="text-base font-semibold text-[#0f172a]">Retry Movex write?</h3>
              <p className="text-sm text-[#475569] mt-1">
                Reset <strong className="font-mono">{confirmRetry.mi_transaction}</strong> on{" "}
                <strong className="font-mono">{confirmRetry.ecn_number}</strong> to pending and
                dispatch it immediately.
              </p>
              {confirmRetry.state === "abandoned" && (
                <p className="text-xs text-amber-600 mt-1.5">
                  This entry was abandoned after {confirmRetry.max_attempts} attempts — retrying
                  starts a fresh attempt cycle.
                </p>
              )}
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setConfirmRetry(null)}>
                Cancel
              </Button>
              <Button
                size="sm"
                disabled={retry.isPending}
                onClick={() => retry.mutate(confirmRetry.id)}
              >
                {retry.isPending ? "…" : "Retry now"}
              </Button>
            </div>
            {retry.isError && (
              <p className="text-xs text-red-600">Retry failed — check the entry state and try again.</p>
            )}
          </div>
        </div>
      )}
    </>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

type AdminTab = "roles" | "outbox" | "customer-defaults" | "ldap"

const ADMIN_TABS: { id: AdminTab; label: string; description: string }[] = [
  {
    id: "roles",
    label: "ECN Role Assignments",
    description: "Default users auto-assigned to each role when a new ECN is created. Hover a row to reveal the remove button.",
  },
  {
    id: "outbox",
    label: "Movex Write Recovery",
    description: "Failed and abandoned Movex writes. Failed entries auto-retry on a schedule; abandoned entries (10 failed attempts) need a manual retry here.",
  },
  {
    id: "customer-defaults",
    label: "Customer — SE / PM Defaults",
    description: "Per-customer Senior Engineer and Production Manager candidates, seeded from Stargile allocation data. Mark one candidate per role as \"Default\" to auto-assign it on ECN creation for that customer.",
  },
  {
    id: "ldap",
    label: "Active Directory Groups",
    description: "Groups under OU=Application Roles,OU=Groups,DC=srxglobal,DC=com",
  },
]

export default function AdminPage() {
  const user = useAuthStore((s) => s.user)
  const isDC = user?.groups?.includes("ecn-doc-controller") ?? false
  const [tab, setTab] = useState<AdminTab>("roles")

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

  const active = ADMIN_TABS.find((t) => t.id === tab) ?? ADMIN_TABS[0]

  return (
    <div className="min-h-screen bg-[#f5f7fa] flex flex-col">
      <header className="sticky top-0 z-[1020] border-b border-[#e8ecf0] bg-white px-6 h-14 flex items-center gap-3 shadow-[var(--shadow-xs)]">
        <Link to="/ecn" className="text-sm text-[#94a3b8] hover:text-[#475569] transition-colors">
          ← ECNs
        </Link>
        <span className="text-[#e2e8f0]">|</span>
        <span className="font-semibold text-sm text-[#1e293b]">Administration</span>
      </header>

      <main className="flex-1 mx-auto w-full max-w-6xl px-6 py-6">
        <div className="flex gap-6 items-start">
          {/* Left nav */}
          <nav className="w-56 shrink-0 sticky top-20 space-y-1">
            {ADMIN_TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={`w-full text-left px-3 py-2 rounded-lg text-sm font-medium transition-colors duration-150 ${
                  tab === t.id
                    ? "bg-[#eff6ff] text-[#0066cc]"
                    : "text-[#475569] hover:bg-white hover:text-[#0f172a]"
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>

          {/* Active section */}
          <section className="flex-1 min-w-0 rounded-xl border border-[#e8ecf0] bg-white shadow-[var(--shadow-sm)] overflow-hidden">
            <div className="px-5 py-4 border-b border-[#f1f5f9] bg-[#f8fafc]">
              <h2 className="text-sm font-semibold text-[#0f172a]">{active.label}</h2>
              <p className="text-xs text-[#94a3b8] mt-0.5">{active.description}</p>
            </div>
            <div className="p-5">
              {tab === "roles" && <RoleAssignmentsSection />}
              {tab === "outbox" && <MovexOutboxSection />}
              {tab === "customer-defaults" && <CustomerRoleDefaultsSection />}
              {tab === "ldap" && <LdapGroupsSection />}
            </div>
          </section>
        </div>
      </main>
    </div>
  )
}
