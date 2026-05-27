import * as React from "react"
import { cn } from "@/lib/utils"

interface SpinnerProps extends React.HTMLAttributes<HTMLDivElement> {
  size?: "sm" | "md" | "lg"
}

export function Spinner({ className, size = "md", ...props }: SpinnerProps) {
  const sizeStyles = {
    sm: "w-4 h-4 border-2",
    md: "w-6 h-6 border-2",
    lg: "w-10 h-10 border-[3px]",
  }
  return (
    <div
      className={cn(
        "inline-block rounded-full animate-spin border-neutral-200 border-t-neutral-700",
        sizeStyles[size],
        className
      )}
      {...props}
    />
  )
}

interface LoadingStateProps extends React.HTMLAttributes<HTMLDivElement> {
  message?: string
  size?: SpinnerProps["size"]
}

export function LoadingState({
  className,
  message = "Loading…",
  size = "md",
  ...props
}: LoadingStateProps) {
  return (
    <div
      className={cn("flex flex-col items-center justify-center gap-3 py-16", className)}
      {...props}
    >
      <Spinner size={size} />
      <p className="text-sm text-neutral-400">{message}</p>
    </div>
  )
}

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  count?: number
}

export function Skeleton({ className, count = 1, ...props }: SkeletonProps) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className={cn(
            "h-4 w-full rounded-md bg-neutral-100 animate-pulse",
            i < count - 1 && "mb-3",
            className
          )}
          {...props}
        />
      ))}
    </>
  )
}
