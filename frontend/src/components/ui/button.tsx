import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-all duration-150 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-[#0066cc] text-white shadow-sm hover:bg-[#0052a3] active:bg-[#003d7a] focus-visible:ring-2 focus-visible:ring-[#0066cc] focus-visible:ring-offset-2",
        destructive:
          "bg-red-600 text-white shadow-sm hover:bg-red-700 active:bg-red-800 focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-2",
        outline:
          "border border-[#d1d9e0] bg-white text-[#0f172a] shadow-[var(--shadow-xs)] hover:bg-[#f5f7fa] hover:border-[#0066cc] hover:text-[#0066cc] focus-visible:ring-2 focus-visible:ring-[#0066cc] focus-visible:ring-offset-2",
        secondary:
          "bg-[#eff6ff] text-[#0066cc] hover:bg-[#dbeafe] focus-visible:ring-2 focus-visible:ring-[#0066cc] focus-visible:ring-offset-2",
        ghost:
          "text-[#475569] hover:bg-[#f5f7fa] hover:text-[#0f172a] focus-visible:ring-2 focus-visible:ring-[#0066cc] focus-visible:ring-offset-2",
        link:
          "text-[#0066cc] underline-offset-4 hover:underline p-0 h-auto shadow-none",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm:      "h-8 rounded-md px-3 text-xs",
        lg:      "h-11 rounded-lg px-6 text-base",
        icon:    "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
