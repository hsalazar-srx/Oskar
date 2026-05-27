import { create } from "zustand"
import axiosInstance from "@/api/axios"

interface AuthUser {
  username: string
  groups: string[]
}

interface AuthState {
  accessToken: string | null
  user: AuthUser | null
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

/** Decode a JWT payload without verifying the signature (client-side only). */
function parseJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const [, payloadB64] = token.split(".")
    const json = atob(payloadB64.replace(/-/g, "+").replace(/_/g, "/"))
    return JSON.parse(json)
  } catch {
    return null
  }
}

/** Returns a user object from a JWT payload, or null if the token is expired. */
function userFromToken(token: string): AuthUser | null {
  const payload = parseJwtPayload(token)
  if (!payload) return null
  // exp is in seconds; Date.now() is in ms
  if (typeof payload.exp === "number" && payload.exp * 1000 < Date.now()) return null
  return {
    username: (payload.sub as string) ?? "",
    groups: (payload.groups as string[]) ?? [],
  }
}

// Rehydrate on startup — parse the stored token if it exists and isn't expired
const storedToken = sessionStorage.getItem("access_token")
const hydratedUser = storedToken ? userFromToken(storedToken) : null

// If the stored token is expired, clear it now so ProtectedRoute sends to /login cleanly
if (storedToken && !hydratedUser) {
  sessionStorage.removeItem("access_token")
}

export const useAuthStore = create<AuthState>(() => ({
  accessToken: hydratedUser ? storedToken : null,
  user: hydratedUser,

  login: async (username, password) => {
    const { data } = await axiosInstance.post("/api/v1/auth/login", { username, password })
    const token: string = data.access_token
    sessionStorage.setItem("access_token", token)
    useAuthStore.setState({
      accessToken: token,
      user: userFromToken(token) ?? { username, groups: [] },
    })
  },

  logout: async () => {
    try {
      await axiosInstance.post("/api/v1/auth/logout")
    } finally {
      sessionStorage.removeItem("access_token")
      useAuthStore.setState({ accessToken: null, user: null })
    }
  },
}))
