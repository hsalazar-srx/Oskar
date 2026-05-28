import { useState, useRef } from "react"

interface Props {
  roleId: string
  roleName?: string
  username: string | null
  isAutoAssigned?: boolean
  canEdit: boolean
  isSaving: boolean
  onSave: (username: string) => void
}

export default function RoleRow({ roleId, roleName, username, isAutoAssigned, canEdit, isSaving, onSave }: Props) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(username ?? "")
  const inputRef = useRef<HTMLInputElement>(null)

  function startEdit() {
    setValue(username ?? "")
    setEditing(true)
    setTimeout(() => inputRef.current?.focus(), 0)
  }

  function handleSave() {
    if (!value.trim()) return
    onSave(value.trim())
    setEditing(false)
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") handleSave()
    if (e.key === "Escape") setEditing(false)
  }

  return (
    <div className="flex items-center gap-2 rounded-md border border-neutral-100 bg-neutral-50 px-3 py-2 group">
      <div className="shrink-0 w-28">
        <span className="text-xs font-medium text-neutral-700 block leading-tight">
          {roleName ?? roleId}
        </span>
        <span className="font-mono text-[10px] text-neutral-400 leading-tight">{roleId}</span>
      </div>
      {editing ? (
        <div className="flex items-center gap-1 flex-1 min-w-0">
          <input
            ref={inputRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1 min-w-0 h-6 text-xs border border-neutral-300 rounded px-1.5 focus:outline-none focus:ring-1 focus:ring-neutral-900 bg-white"
            placeholder="username"
          />
          <button
            onClick={handleSave}
            disabled={isSaving || !value.trim()}
            className="text-xs text-neutral-600 hover:text-neutral-900 disabled:opacity-40 shrink-0"
          >
            {isSaving ? "…" : "✓"}
          </button>
          <button
            onClick={() => setEditing(false)}
            className="text-xs text-neutral-400 hover:text-neutral-700 shrink-0"
          >
            ✕
          </button>
        </div>
      ) : (
        <>
          <span className="text-xs text-neutral-600 truncate flex-1">
            {username ?? <em className="text-neutral-300">unassigned</em>}
            {isAutoAssigned && (
              <span className="ml-1.5 text-[10px] text-neutral-300" title="Auto-assigned from system roster">auto</span>
            )}
          </span>
          {canEdit && (
            <button
              onClick={startEdit}
              className="text-neutral-300 hover:text-neutral-600 opacity-0 group-hover:opacity-100 transition-opacity duration-[150ms] shrink-0 text-xs"
              title="Reassign role"
            >
              ✎
            </button>
          )}
        </>
      )}
    </div>
  )
}
