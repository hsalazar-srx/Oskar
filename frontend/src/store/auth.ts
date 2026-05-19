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

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: sessionStorage.getItem("access_token"),
  user: null,

  login: async (username, password) => {
    const { data } = await axiosInstance.post("/auth/login", { username, password })
    sessionStorage.setItem("access_token", data.access_token)
    set({ accessToken: data.access_token, user: data.user ?? { username, groups: [] } })
  },

  logout: async () => {
    try {
      await axiosInstance.post("/auth/logout")
    } finally {
      sessionStorage.removeItem("access_token")
      set({ accessToken: null, user: null })
    }
  },
}))
