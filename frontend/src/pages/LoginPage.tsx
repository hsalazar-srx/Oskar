import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuthStore } from "@/store/auth"

const schema = z.object({
  username: z.string().min(1, "Required"),
  password: z.string().min(1, "Required"),
})
type FormValues = z.infer<typeof schema>

export default function LoginPage() {
  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)
  const [error, setError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  const onSubmit = async (data: FormValues) => {
    setError(null)
    try {
      await login(data.username, data.password)
      navigate("/ecn", { replace: true })
    } catch {
      setError("Invalid username or password")
    }
  }

  return (
    <div className="flex min-h-screen bg-[#f5f7fa]">
      {/* Left brand panel */}
      <div className="hidden lg:flex lg:w-[45%] flex-col justify-between bg-[#0066cc] p-12 text-white relative overflow-hidden">
        {/* Subtle geometric background */}
        <div className="absolute inset-0 opacity-10">
          <div className="absolute -top-32 -right-32 w-96 h-96 rounded-full border-[64px] border-white" />
          <div className="absolute -bottom-20 -left-20 w-72 h-72 rounded-full border-[48px] border-white" />
        </div>

        <div className="relative z-10">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-white/20 flex items-center justify-center">
              <span className="text-white font-bold text-sm">O</span>
            </div>
            <span className="text-lg font-semibold tracking-tight">Oskar</span>
            <span className="rounded-md bg-white/15 px-2 py-0.5 text-xs font-medium font-mono">ECN</span>
          </div>
        </div>

        <div className="relative z-10 space-y-4">
          <h1 className="text-4xl font-bold leading-tight">
            Engineering Change
          </h1>
          <p className="text-blue-100/80 text-sm leading-relaxed max-w-xs">
            Structured ECN workflow for Scanfil APAC — engineering, quality, and document control in one place.
          </p>
        </div>

        <div className="relative z-10 flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-white/40" />
          <p className="text-xs text-blue-200/70">Scanfil APAC · Internal system</p>
        </div>
      </div>

      {/* Right login form */}
      <div className="flex flex-1 items-center justify-center px-6 py-16">
        <div className="w-full max-w-sm">
          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-2 mb-10">
            <div className="w-8 h-8 rounded-lg bg-[#0066cc] flex items-center justify-center">
              <span className="text-white font-bold text-sm">O</span>
            </div>
            <span className="text-lg font-semibold tracking-tight">Oskar</span>
          </div>

          <div className="space-y-1.5 mb-8">
            <h2 className="text-2xl font-bold tracking-tight text-[#0f172a]">Welcome back</h2>
            <p className="text-sm text-[#94a3b8]">Sign in with your network credentials</p>
          </div>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="username" className="text-sm font-medium text-[#475569]">
                Username
              </Label>
              <Input
                id="username"
                autoComplete="username"
                autoFocus
                className="h-10 border-[#d1d9e0] bg-white focus:border-[#0066cc] focus:ring-[#0066cc]"
                {...register("username")}
              />
              {errors.username && (
                <p className="text-xs text-red-500 mt-1">{errors.username.message}</p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password" className="text-sm font-medium text-[#475569]">
                Password
              </Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                className="h-10 border-[#d1d9e0] bg-white focus:border-[#0066cc] focus:ring-[#0066cc]"
                {...register("password")}
              />
              {errors.password && (
                <p className="text-xs text-red-500 mt-1">{errors.password.message}</p>
              )}
            </div>

            {error && (
              <div className="flex items-center gap-2.5 rounded-lg border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-700">
                <svg className="w-4 h-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clipRule="evenodd"/>
                </svg>
                <span>{error}</span>
              </div>
            )}

            <Button type="submit" className="w-full h-10 mt-2" disabled={isSubmitting}>
              {isSubmitting
                ? <span className="flex items-center gap-2"><span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />Signing in…</span>
                : "Sign in"
              }
            </Button>
          </form>
        </div>
      </div>
    </div>
  )
}
