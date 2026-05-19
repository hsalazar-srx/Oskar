import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { useAuthStore } from "@/store/auth"

// Pages — created in S4-12 through S4-16
// Placeholder until each page is built
function Placeholder({ name }: { name: string }) {
  return (
    <div className="flex h-screen items-center justify-center text-neutral-400">
      <span className="font-mono text-sm">{name} — coming soon</span>
    </div>
  )
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.accessToken)
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Placeholder name="LoginPage" />} />
          <Route
            path="/ecn"
            element={
              <ProtectedRoute>
                <Placeholder name="ECNListPage" />
              </ProtectedRoute>
            }
          />
          <Route
            path="/ecn/new"
            element={
              <ProtectedRoute>
                <Placeholder name="ECNCreatePage" />
              </ProtectedRoute>
            }
          />
          <Route
            path="/ecn/:id"
            element={
              <ProtectedRoute>
                <Placeholder name="ECNDetailPage" />
              </ProtectedRoute>
            }
          />
          <Route path="/" element={<Navigate to="/ecn" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
