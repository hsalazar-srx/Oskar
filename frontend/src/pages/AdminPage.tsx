import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { Spinner } from "@/components/ui/spinner"
import { useAuthStore } from "@/store/auth"
import axiosInstance from "@/api/axios"
import { ROLE_LABEL } from "@/lib/ecn-workflow"

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

// ── Helpers ────────────────────────────────────────────────────────────────────

const VALID_ROLE_IDS = [
  "DC", "OR", "SE", "CE", "EM", "QM", "PM", "SC", "FN", "AD", "CA", "RD", "TE", "MQ",
]

function groupPrefix(cn: string): string {
  const m = cn.match(/^([a-z]+)-/)
  return m ? m[1].toUpperCase() : "OTHER"
}

const APP_PREFIX_LABEL: Record<string, string> = {
  ECN: "Engineering Change Notice",
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

// ── ECN Role Assignments section ──────────────────────────────────────────────

function RoleAssignmentsSection() {
  const { data: users = [], isLoading } = useQuery({
    queryKey: ["admin-roles"],
    queryFn: fetchRoleUsers,
    staleTime: 0,
  })

  const grouped = VALID_ROLE_IDS.reduce<Record<string, RoleUser[]>>((acc, r) => {
    const rows = users.filter((u) => u.role_id === r && u.is_active)
    if (rows.length) acc[r] = rows
    return acc
  }, {})

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-[#94a3b8]">
        <Spinner size="sm" /> Loading role assignments…
      </div>
    )
  }

  if (Object.keys(grouped).length === 0) {
    return (
      <p className="text-sm text-[#94a3b8] py-8 text-center">No active role assignments configured.</p>
    )
  }

  return (
    <div className="space-y-2">
      {Object.entries(grouped).map(([roleId, rows]) => (
        <div key={roleId} className="rounded-lg border border-[#e8ecf0] overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-2.5 bg-[#f8fafc] border-b border-[#f1f5f9]">
            <span className="font-mono text-xs font-bold text-[#0066cc]">{roleId}</span>
            <span className="text-sm text-[#475569]">{ROLE_LABEL[roleId] ?? roleId}</span>
            <Badge variant="secondary" className="ml-auto text-[11px]">
              {rows.length}
            </Badge>
          </div>
          <div className="divide-y divide-[#f8fafc]">
            {rows.map((u) => (
              <div key={u.id} className="flex items-center gap-3 px-4 py-2.5">
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
                  <span className="text-[11px] text-[#94a3b8]">Facility: <strong className="text-[#475569]">{u.facility}</strong></span>
                  {u.email && (
                    <span className="text-xs text-[#94a3b8] hidden sm:block">{u.email}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
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
      <header className="sticky top-0 z-[1020] border-b border-[#e8ecf0] bg-white px-6 h-14 flex items-center gap-3 shadow-[var(--shadow-xs)]">
        <Link to="/ecn" className="text-sm text-[#94a3b8] hover:text-[#475569] transition-colors">
          ← ECNs
        </Link>
        <span className="text-[#e2e8f0]">|</span>
        <span className="font-semibold text-sm text-[#1e293b]">Administration</span>
        <span className="ml-auto text-xs text-[#94a3b8]">Read-only view</span>
      </header>

      <main className="flex-1 mx-auto w-full max-w-4xl px-6 py-6 space-y-6">
        {/* LDAP groups */}
        <section className="rounded-xl border border-[#e8ecf0] bg-white shadow-[var(--shadow-sm)] overflow-hidden">
          <div className="px-5 py-4 border-b border-[#f1f5f9] bg-[#f8fafc]">
            <h2 className="text-sm font-semibold text-[#0f172a]">Active Directory — Application Role Groups</h2>
            <p className="text-xs text-[#94a3b8] mt-0.5">
              Groups under <span className="font-mono">OU=Application Roles,OU=Groups,DC=srxglobal,DC=com</span>
            </p>
          </div>
          <div className="p-5">
            <LdapGroupsSection />
          </div>
        </section>

        {/* ECN role assignments */}
        <section className="rounded-xl border border-[#e8ecf0] bg-white shadow-[var(--shadow-sm)] overflow-hidden">
          <div className="px-5 py-4 border-b border-[#f1f5f9] bg-[#f8fafc]">
            <h2 className="text-sm font-semibold text-[#0f172a]">Oskar — ECN Role Assignments</h2>
            <p className="text-xs text-[#94a3b8] mt-0.5">
              Active assignments from <span className="font-mono">system_role_users</span> — controls who is auto-assigned to each ECN role
            </p>
          </div>
          <div className="p-5">
            <RoleAssignmentsSection />
          </div>
        </section>
      </main>
    </div>
  )
}
