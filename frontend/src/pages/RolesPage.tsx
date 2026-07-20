import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertCircle, Loader2, Lock, Save } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { usePermission } from "@/lib/auth"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/Badge"
import { PageHeader } from "@/components/ui/PageHeader"
import { SkeletonCard } from "@/components/ui/skeleton"

type Role = {
  id: string
  slug: string
  name: string
  description: string | null
  is_system: boolean
  permission_codes: string[]
  users_count: number
}

type Permission = { id: string; code: string; module: string; description: string }

export default function RolesPage() {
  const qc = useQueryClient()
  const canEdit = usePermission("roles.editar")

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [draft, setDraft] = useState<Set<string> | null>(null)

  const rolesQ = useQuery({
    queryKey: ["roles"],
    queryFn: async () => (await api.get<Role[]>(`${API_PREFIX}/roles`)).data,
  })
  const permsQ = useQuery({
    queryKey: ["roles", "permissions"],
    queryFn: async () => (await api.get<Permission[]>(`${API_PREFIX}/roles/permissions`)).data,
  })

  const roles = rolesQ.data ?? []
  const selected = roles.find((r) => r.id === selectedId) ?? roles[0] ?? null
  const isAdminRole = selected?.slug === "administrador"

  // Permisos agrupados por módulo, para pintar la matriz por secciones.
  const byModule = useMemo(() => {
    const map = new Map<string, Permission[]>()
    for (const p of permsQ.data ?? []) {
      const list = map.get(p.module) ?? []
      list.push(p)
      map.set(p.module, list)
    }
    return [...map.entries()]
  }, [permsQ.data])

  const current = draft ?? new Set(selected?.permission_codes ?? [])
  const dirty = draft !== null

  const save = useMutation({
    mutationFn: async () => {
      if (!selected || !draft) return
      await api.patch(`${API_PREFIX}/roles/${selected.id}`, {
        permission_codes: [...draft],
      })
    },
    onSuccess: () => {
      setDraft(null)
      qc.invalidateQueries({ queryKey: ["roles"] })
    },
  })

  const toggle = (code: string) => {
    const next = new Set(current)
    if (next.has(code)) next.delete(code)
    else next.add(code)
    setDraft(next)
  }

  const isLoading = rolesQ.isLoading || permsQ.isLoading

  return (
    <div>
      <PageHeader
        title="Roles y permisos"
        description="Cada rol agrupa permisos granulares. Los cambios aplican al instante a los usuarios asignados."
      />

      {isLoading ? (
        <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
          <SkeletonCard />
          <SkeletonCard className="h-80" />
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
          {/* Lista de roles */}
          <div className="space-y-1.5">
            {roles.map((r) => (
              <button
                key={r.id}
                onClick={() => {
                  setSelectedId(r.id)
                  setDraft(null)
                }}
                className={cn(
                  "w-full rounded-lg border p-3 text-left transition",
                  selected?.id === r.id
                    ? "border-primary bg-primary/5"
                    : "border-border hover:bg-accent",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{r.name}</span>
                  {r.is_system && <Lock className="h-3 w-3 shrink-0 text-muted-foreground" />}
                </div>
                <div className="mt-1.5 flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="tabular">{r.permission_codes.length} permisos</span>
                  <span>·</span>
                  <span className="tabular">{r.users_count} usuarios</span>
                </div>
              </button>
            ))}
          </div>

          {/* Matriz de permisos */}
          {selected && (
            <div className="rounded-lg border border-border">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3.5">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-semibold">{selected.name}</h2>
                    {selected.is_system && <Badge tone="info">Rol de sistema</Badge>}
                  </div>
                  {selected.description && (
                    <p className="mt-0.5 text-xs text-muted-foreground">{selected.description}</p>
                  )}
                </div>

                {canEdit && !isAdminRole && (
                  <button
                    onClick={() => save.mutate()}
                    disabled={!dirty || save.isPending}
                    className="flex items-center gap-2 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-white transition hover:bg-primary/90 disabled:opacity-40"
                  >
                    {save.isPending ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Save className="h-3.5 w-3.5" />
                    )}
                    Guardar
                  </button>
                )}
              </div>

              {isAdminRole && (
                <p className="border-b border-border bg-muted/40 px-5 py-2.5 text-xs text-muted-foreground">
                  El rol Administrador conserva todos los permisos y no puede recortarse: evita
                  dejar el sistema sin nadie capaz de repararlo.
                </p>
              )}

              {save.isError && (
                <div className="flex items-start gap-2 border-b border-border bg-state-danger/10 px-5 py-2.5 text-xs text-state-danger">
                  <AlertCircle className="mt-px h-3.5 w-3.5 shrink-0" />
                  {apiErrorMessage(save.error, "No se pudieron guardar los permisos")}
                </div>
              )}

              <div className="divide-y divide-border">
                {byModule.map(([module, perms]) => (
                  <div key={module} className="px-5 py-3.5">
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {module}
                    </h3>
                    <div className="mt-2.5 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                      {perms.map((p) => (
                        <label
                          key={p.id}
                          className={cn(
                            "flex items-start gap-2.5 rounded-md px-2 py-1.5 text-sm",
                            canEdit && !isAdminRole
                              ? "cursor-pointer hover:bg-accent"
                              : "cursor-not-allowed opacity-70",
                          )}
                        >
                          <input
                            type="checkbox"
                            checked={current.has(p.code)}
                            disabled={!canEdit || isAdminRole}
                            onChange={() => toggle(p.code)}
                            className="mt-0.5 h-3.5 w-3.5 accent-[var(--primary)]"
                          />
                          <span>
                            <span className="block leading-tight">{p.description}</span>
                            <code className="text-[11px] text-muted-foreground">{p.code}</code>
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
