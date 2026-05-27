import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default:     "border-transparent bg-neutral-900 text-white",
        secondary:   "border-transparent bg-neutral-100 text-neutral-700",
        outline:     "border-neutral-300 text-neutral-700",
        destructive: "border-transparent bg-red-100 text-red-700",
        // ── Semantic status variants ───────────────────────────────────────
        success:     "border-green-200 bg-green-50 text-green-700",
        warning:     "border-amber-200 bg-amber-50 text-amber-700",
        error:       "border-red-200 bg-red-50 text-red-700",
        info:        "border-blue-200 bg-blue-50 text-blue-700",
        purple:      "border-violet-200 bg-violet-50 text-violet-700",
        teal:        "border-teal-200 bg-teal-50 text-teal-700",
        neutral:     "border-neutral-200 bg-neutral-100 text-neutral-500",
        orange:      "border-orange-200 bg-orange-50 text-orange-700",
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
