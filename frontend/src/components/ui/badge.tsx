import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset transition-colors",
  {
    variants: {
      variant: {
        default:     "bg-[#0f172a] text-white ring-transparent",
        secondary:   "bg-[#f1f5f9] text-[#475569] ring-[#e2e8f0]",
        outline:     "bg-transparent text-[#475569] ring-[#cbd5e1]",
        destructive: "bg-red-50 text-red-700 ring-red-200",
        // ── Semantic status variants ───────────────────────────────────────
        success:     "bg-emerald-50 text-emerald-700 ring-emerald-200",
        warning:     "bg-amber-50 text-amber-700 ring-amber-200",
        error:       "bg-red-50 text-red-700 ring-red-200",
        info:        "bg-blue-50 text-[#0066cc] ring-blue-200",
        purple:      "bg-violet-50 text-violet-700 ring-violet-200",
        teal:        "bg-teal-50 text-teal-700 ring-teal-200",
        neutral:     "bg-slate-100 text-slate-500 ring-slate-200",
        orange:      "bg-orange-50 text-orange-700 ring-orange-200",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
