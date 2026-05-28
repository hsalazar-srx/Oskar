import { Button } from "@/components/ui/button"

// ── ModalField ────────────────────────────────────────────────────────────────

interface ModalFieldProps {
  name: string
  label: string
  type?: "date"
  multiline?: boolean
  placeholder?: string
  required?: boolean
}

export function ModalField({ name, label, type, multiline, placeholder, required }: ModalFieldProps) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={name} className="text-sm font-medium text-neutral-700">
        {label}{required && <span className="text-red-400 ml-0.5">*</span>}
      </label>
      {multiline ? (
        <textarea
          id={name}
          name={name}
          rows={3}
          required={required}
          placeholder={placeholder}
          className="w-full rounded-md border border-neutral-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900 resize-none"
        />
      ) : (
        <input
          id={name}
          name={name}
          type={type ?? "text"}
          required={required}
          placeholder={placeholder}
          className="w-full rounded-md border border-neutral-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900"
        />
      )}
    </div>
  )
}

// ── ActionModal ───────────────────────────────────────────────────────────────

interface ActionModalProps {
  title: string
  description?: string
  confirmLabel: string
  confirmVariant?: "default" | "destructive"
  onConfirm: (data: Record<string, string>) => void
  onCancel: () => void
  isPending?: boolean
  children: React.ReactNode
}

export function ActionModal({
  title,
  description,
  confirmLabel,
  confirmVariant = "default",
  onConfirm,
  onCancel,
  isPending,
  children,
}: ActionModalProps) {
  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    const data: Record<string, string> = {}
    fd.forEach((v, k) => { data[k] = v as string })
    onConfirm(data)
  }

  return (
    <div
      className="fixed inset-0 z-[1080] flex items-center justify-center bg-black/40"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel() }}
    >
      <div className="w-full max-w-md rounded-lg bg-white shadow-xl mx-4">
        <div className="px-5 pt-5 pb-2">
          <h3 className="text-base font-semibold text-neutral-900">{title}</h3>
          {description && <p className="text-sm text-neutral-500 mt-1">{description}</p>}
        </div>
        <form onSubmit={handleSubmit}>
          <div className="px-5 py-3 space-y-4">
            {children}
          </div>
          <div className="flex justify-end gap-2 px-5 py-4 border-t">
            <Button type="button" variant="outline" size="sm" onClick={onCancel}>
              Cancel
            </Button>
            <Button
              type="submit"
              size="sm"
              variant={confirmVariant}
              disabled={isPending}
            >
              {isPending ? "…" : confirmLabel}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
