import axios, { type AxiosRequestConfig } from "axios"

export const axiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "/api/v1",
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

// On 401 attempt a token refresh; redirect to /login on failure
axiosInstance.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config as AxiosRequestConfig & { _retry?: boolean }
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true
      try {
        const { data } = await axiosInstance.post("/auth/refresh")
        sessionStorage.setItem("access_token", data.access_token)
        axiosInstance.defaults.headers.common.Authorization = `Bearer ${data.access_token}`
        return axiosInstance(original)
      } catch {
        sessionStorage.removeItem("access_token")
        window.location.href = "/login"
      }
    }
    return Promise.reject(error)
  },
)

export default axiosInstance
