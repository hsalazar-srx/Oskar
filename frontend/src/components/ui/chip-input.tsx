import * as React from "react"
import { cn } from "@/lib/utils"
import { parseDesignators } from "@/lib/designators"

/**
 * Token input for reference designators (circuit refs).
 *
 * Replaces the plain comma-joined text field the BOM change forms used. With
 * a text field there was no way to see how many designators you had entered,
 * no way to remove one without re-editing a long string, and a stray comma
 * silently produced an empty designator.
 *
 * Parsing and range expansion (`R1-R5` → R1…R5) live in @/lib/designators.
 */

interface ChipInputProps {
  value: string[]
  onChange: (next: string[]) => void
  placeholder?: string
  disabled?: boolean
  className?: string
  "aria-label"?: string
}

export function ChipInput({
  value,
  onChange,
  placeholder = "R1, R7, R12  (R1-R5 expands)",
  disabled = false,
  className,
  "aria-label": ariaLabel,
}: ChipInputProps) {
  const [draft, setDraft] = React.useState("")
  const inputRef = React.useRef<HTMLInputElement>(null)

  function commit(raw: string) {
    const parsed = parseDesignators(raw)
    if (parsed.length === 0) return
    // De-dupe against what is already there, preserving existing order.
    const existing = new Set(value)
    const additions = parsed.filter((p) => !existing.has(p))
    if (additions.length > 0) onChange([...value, ...additions])
    setDraft("")
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === "," || e.key === "Tab") {
      if (draft.trim()) {
        // Tab still moves focus when there is nothing to commit, so the
        // field does not trap keyboard users.
        e.preventDefault()
        commit(draft)
      }
      return
    }
    // Backspace on an empty draft removes the last chip — standard token-input
    // behaviour, and the fastest way to undo a mistyped entry.
    if (e.key === "Backspace" && !draft && value.length > 0) {
      onChange(value.slice(0, -1))
    }
  }

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-1 rounded-md border border-neutral-200 bg-white px-2 py-1.5",
        "focus-within:ring-2 focus-within:ring-neutral-900 focus-within:ring-offset-1",
        disabled && "cursor-not-allowed opacity-50",
        className
      )}
      onClick={() => inputRef.current?.focus()}
    >
      {value.map((chip) => (
        <span
          key={chip}
          className="inline-flex items-center gap-1 rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-[11px] text-neutral-700"
        >
          {chip}
          {!disabled && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                onChange(value.filter((c) => c !== chip))
              }}
              className="text-neutral-400 hover:text-red-600"
              aria-label={`Remove ${chip}`}
            >
              ×
            </button>
          )}
        </span>
      ))}
      <input
        ref={inputRef}
        value={draft}
        disabled={disabled}
        aria-label={ariaLabel ?? "Reference designators"}
        onChange={(e) => {
          // Typing/pasting a comma commits immediately, so pasting a whole
          // "R1,R2,R3" string from a CAD tool does the right thing.
          if (e.target.value.includes(",")) commit(e.target.value)
          else setDraft(e.target.value)
        }}
        onKeyDown={handleKeyDown}
        onBlur={() => draft.trim() && commit(draft)}
        placeholder={value.length === 0 ? placeholder : ""}
        className="min-w-[8rem] flex-1 bg-transparent text-xs font-mono outline-none placeholder:font-sans placeholder:text-neutral-400 disabled:cursor-not-allowed"
      />
    </div>
  )
}
