import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios"

import { useAuth } from "./auth"

export const API_PREFIX = "/api/v1"

/** Cliente HTTP único. Vite hace proxy de /api -> http://localhost:8000 en dev. */
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "",
  headers: { "Content-Type": "application/json" },
})

api.interceptors.request.use((config) => {
  const token = useAuth.getState().accessToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Un único refresh en vuelo: si varias peticiones reciben 401 a la vez,
// todas esperan al mismo intento en vez de disparar N refrescos.
let refreshing: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const { refreshToken, setTokens, logout } = useAuth.getState()
  if (!refreshToken) return null

  try {
    const { data } = await axios.post<{ access_token: string; refresh_token: string }>(
      `${API_PREFIX}/auth/refresh`,
      { refresh_token: refreshToken },
    )
    setTokens(data.access_token, data.refresh_token)
    return data.access_token
  } catch {
    logout()
    return null
  }
}

api.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retried?: boolean }

    const isAuthCall = original?.url?.includes("/auth/refresh") || original?.url?.includes("/auth/login")
    if (error.response?.status !== 401 || original?._retried || isAuthCall) {
      return Promise.reject(error)
    }

    original._retried = true
    refreshing ??= refreshAccessToken().finally(() => {
      refreshing = null
    })

    const token = await refreshing
    if (!token) return Promise.reject(error)

    original.headers.Authorization = `Bearer ${token}`
    return api(original)
  },
)

/** Extrae el `detail` de FastAPI para mostrarlo al usuario. */
export function apiErrorMessage(error: unknown, fallback = "Ocurrió un error inesperado"): string {
  if (error instanceof AxiosError) {
    const detail = error.response?.data?.detail
    if (typeof detail === "string") return detail
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg)
    if (error.code === "ERR_NETWORK") return "No hay conexión con el servidor"
  }
  return fallback
}
