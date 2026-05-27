import axios, { type AxiosRequestConfig } from "axios"

export const axiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "",
  withCredentials: true,
})

// Attach Bearer token from sessionStorage on every request
axiosInstance.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("access_token")
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// On 401: attempt a token refresh; if that also fails, clear everything and go to /login
axiosInstance.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config as AxiosRequestConfig & { _retry?: boolean }

    // Don't retry auth endpoints — avoids infinite loops on login/refresh/logout
    const isAuthEndpoint = (original.url ?? "").includes("/auth/")

    if (error.response?.status === 401 && !original._retry && !isAuthEndpoint) {
      original._retry = true
      try {
        const { data } = await axiosInstance.post("/api/v1/auth/refresh")
        const newToken: string = data.access_token
        sessionStorage.setItem("access_token", newToken)
        axiosInstance.defaults.headers.common.Authorization = `Bearer ${newToken}`
        // Patch the original request with the new token and retry
        if (original.headers) {
          original.headers.Authorization = `Bearer ${newToken}`
        }
        return axiosInstance(original)
      } catch {
        // Refresh failed — clear all auth state and redirect to login
        sessionStorage.removeItem("access_token")
        delete axiosInstance.defaults.headers.common.Authorization
        window.location.href = "/login"
      }
    }

    return Promise.reject(error)
  },
)

export default axiosInstance
