import { useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { Navigate, useLocation } from "react-router-dom"
import { ShieldAlert } from "lucide-react"

import { api, API_PREFIX } from "@/lib/api"
import { useAuth, type Me } from "@/lib/auth"
import { SkeletonStatCard } from "@/components/ui/skeleton"

/**
 * Revalida la sesión contra /auth/me en cada arranque. El token persiste en
 * localStorage, pero los permisos NO: así un cambio de rol aplica de inmediato.
 */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { accessToken, me, setMe, logout } = useAuth()
  const location = useLocation()

  const { data, isLoading, isError } = useQuery({
    queryKey: ["auth", "me"],
    queryFn: async () => (await api.get<Me>(`${API_PREFIX}/auth/me`)).data,
    enabled: Boolean(accessToken),
    retry: false,
    staleTime: 5 * 60_000,
  })

  useEffect(() => {
    if (data) setMe(data)
  }, [data, setMe])

  useEffect(() => {
    if (isError) logout()
  }, [isError, logout])

  if (!accessToken) return <Navigate to="/login" state={{ from: location }} replace />
  if (isError) return <Navigate to="/login" replace />

  if (isLoading || !me) {
    return (
      <div className="grid min-h-screen place-items-center bg-background p-6">
        <div className="w-full max-w-sm">
          <SkeletonStatCard />
        </div>
      </div>
    )
  }

  return <>{children}</>
}

/** Corta el acceso a una ruta cuando falta el permiso. */
export function RequirePermission({
  permission,
  children,
}: {
  permission: string
  children: React.ReactNode
}) {
  const me = useAuth((s) => s.me)

  if (me && !me.permission_codes.includes(permission)) {
    return (
      <div className="grid h-full place-items-center">
        <div className="max-w-sm text-center">
          <ShieldAlert className="mx-auto h-10 w-10 text-muted-foreground" />
          <h2 className="mt-4 text-base font-semibold">Sin acceso</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Tu rol <span className="font-medium text-foreground">{me.role.name}</span> no tiene el
            permiso <code className="rounded bg-muted px-1 py-0.5 text-xs">{permission}</code>.
          </p>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
