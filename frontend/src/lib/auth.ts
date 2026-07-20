import { create } from "zustand"
import { persist } from "zustand/middleware"

export type Me = {
  id: string
  email: string
  full_name: string
  dni: string | null
  phone: string | null
  is_active: boolean
  role: { id: string; slug: string; name: string }
  permission_codes: string[]
  last_login_at: string | null
  created_at: string
}

type AuthState = {
  accessToken: string | null
  refreshToken: string | null
  me: Me | null
  setTokens: (access: string, refresh: string) => void
  setMe: (me: Me | null) => void
  logout: () => void
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      me: null,
      setTokens: (accessToken, refreshToken) => set({ accessToken, refreshToken }),
      setMe: (me) => set({ me }),
      logout: () => set({ accessToken: null, refreshToken: null, me: null }),
    }),
    {
      name: "zx-auth",
      // `me` no se persiste: se revalida contra /auth/me en cada arranque,
      // así un cambio de rol se refleja sin tener que cerrar sesión.
      partialize: (s) => ({ accessToken: s.accessToken, refreshToken: s.refreshToken }),
    },
  ),
)

/** Chequeo de permiso para pintar/ocultar UI. El backend siempre revalida. */
export function usePermission(code: string): boolean {
  return useAuth((s) => s.me?.permission_codes.includes(code) ?? false)
}

export function useHasAnyPermission(codes: string[]): boolean {
  return useAuth((s) => {
    if (!s.me) return false
    const granted = new Set(s.me.permission_codes)
    return codes.some((c) => granted.has(c))
  })
}
