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
    <div className="flex min-h-screen bg-neutral-50">
      {/* Left accent panel */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between bg-neutral-900 p-12 text-white">
        <div>
          <span className="text-xl font-bold tracking-tight">Oskar</span>
          <span className="ml-2 rounded bg-neutral-700 px-2 py-0.5 text-xs text-neutral-300 font-mono">ECN</span>
        </div>
        <div className="space-y-3">
          <h1 className="text-3xl font-semibold leading-snug">
            Engineering Change<br />Management
          </h1>
          <p className="text-neutral-400 text-sm leading-relaxed max-w-xs">
            Scanfil APAC — Melbourne facility. Manage engineering changes from draft through Movex implementation.
          </p>
        </div>
        <p className="text-xs text-neutral-600">Scanfil APAC · Internal system</p>
      </div>

      {/* Right login form */}
      <div className="flex flex-1 items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm space-y-8">
          {/* Mobile logo */}
          <div className="lg:hidden">
            <span className="text-xl font-bold tracking-tight">Oskar</span>
            <span className="ml-2 rounded bg-neutral-100 px-2 py-0.5 text-xs text-neutral-500 font-mono">ECN</span>
          </div>

          <div className="space-y-1">
            <h2 className="text-2xl font-semibold tracking-tight">Sign in</h2>
            <p className="text-sm text-neutral-500">Enter your network credentials to continue</p>
          </div>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                autoComplete="username"
                autoFocus
                className="h-10"
                {...register("username")}
              />
              {errors.username && (
                <p className="text-xs text-red-500">{errors.username.message}</p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                className="h-10"
                {...register("password")}
              />
              {errors.password && (
                <p className="text-xs text-red-500">{errors.password.message}</p>
              )}
            </div>

            {error && (
              <div className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
                <span>⚠</span>
                <span>{error}</span>
              </div>
            )}

            <Button type="submit" className="w-full h-10" disabled={isSubmitting}>
              {isSubmitting ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </div>
      </div>
    </div>
  )
}
