import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { useAuthStore } from "@/store/auth"
import LoginPage from "@/pages/LoginPage"
import ECNListPage from "@/pages/ECNListPage"
import ECNCreatePage from "@/pages/ECNCreatePage"
import ECNDetailPage from "@/pages/ECNDetailPage"

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
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/ecn"
            element={<ProtectedRoute><ECNListPage /></ProtectedRoute>}
          />
          <Route
            path="/ecn/new"
            element={<ProtectedRoute><ECNCreatePage /></ProtectedRoute>}
          />
          <Route
            path="/ecn/:id"
            element={<ProtectedRoute><ECNDetailPage /></ProtectedRoute>}
          />
          <Route path="/" element={<Navigate to="/ecn" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
