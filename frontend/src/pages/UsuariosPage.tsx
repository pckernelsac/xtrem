import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Archive, ArchiveRestore, Pencil, Plus, Search, Trash2 } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { useAuth, usePermission } from "@/lib/auth"
import { Badge } from "@/components/ui/Badge"
import { ConfirmarEliminar } from "@/components/ui/ConfirmarEliminar"
import { Button, FormError } from "@/components/ui/Form"
import { FilterTabs } from "@/components/ui/FilterTabs"
import { PageHeader } from "@/components/ui/PageHeader"
import { Paginacion } from "@/components/ui/Paginacion"
import { SkeletonTable } from "@/components/ui/skeleton"
import type { Page } from "@/features/clientes/types"
import { UsuarioFormModal, type Usuario } from "@/features/usuarios/UsuarioFormModal"

type Tab = "todos" | "activos" | "inactivos"
const PAGE_SIZE = 25

const fmtDate = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleDateString("es-PE", { day: "2-digit", month: "short", year: "numeric" })
    : "—"

export default function UsuariosPage() {
  const canCreate = usePermission("usuarios.crear")
  const canEdit = usePermission("usuarios.editar")
  const canDelete = usePermission("usuarios.eliminar")

  const [tab, setTab] = useState<Tab>("todos")
  const [search, setSearch] = useState("")
  const [debounced, setDebounced] = useState("")
  const [page, setPage] = useState(1)
  const meId = useAuth((s) => s.me?.id)

  const [editando, setEditando] = useState<Usuario | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [porEliminar, setPorEliminar] = useState<Usuario | null>(null)

  const qc = useQueryClient()
  const refrescar = () => qc.invalidateQueries({ queryKey: ["usuarios"] })

  // Debounce: la búsqueda la resuelve el servidor, porque la lista viene
  // paginada y en el cliente sólo tenemos la página actual.
  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search)
      setPage(1)
    }, 300)
    return () => clearTimeout(t)
  }, [search])

  const activeFilter = tab === "todos" ? undefined : tab === "activos"

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["usuarios", { tab, debounced, page }],
    queryFn: async () =>
      (
        await api.get<Page<Usuario>>(`${API_PREFIX}/usuarios`, {
          params: {
            search: debounced || undefined,
            is_active: activeFilter,
            page,
            page_size: PAGE_SIZE,
          },
        })
      ).data,
    placeholderData: (prev) => prev,
  })

  // Contadores por pestaña: consultas ligeras que sólo leen el total.
  const countsQ = useQuery({
    queryKey: ["usuarios", "counts", debounced],
    queryFn: async () => {
      const params = { search: debounced || undefined, page_size: 1 }
      const [todos, activos, inactivos] = await Promise.all([
        api.get<Page<Usuario>>(`${API_PREFIX}/usuarios`, { params }),
        api.get<Page<Usuario>>(`${API_PREFIX}/usuarios`, {
          params: { ...params, is_active: true },
        }),
        api.get<Page<Usuario>>(`${API_PREFIX}/usuarios`, {
          params: { ...params, is_active: false },
        }),
      ])
      return {
        todos: todos.data.total,
        activos: activos.data.total,
        inactivos: inactivos.data.total,
      }
    },
  })

  const archivar = useMutation({
    mutationFn: async ({ id, activo }: { id: string; activo: boolean }) => {
      await api.patch(`${API_PREFIX}/usuarios/${id}`, { is_active: activo })
    },
    onSuccess: refrescar,
  })

  const eliminar = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`${API_PREFIX}/usuarios/${id}`)
    },
    onSuccess: () => {
      refrescar()
      setPorEliminar(null)
    },
  })

  const rows = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div>
      <PageHeader
        title="Usuarios"
        description="Cuentas del sistema y el rol asignado a cada una."
        actions={
          canCreate && (
            <Button
              onClick={() => {
                setEditando(null)
                setFormOpen(true)
              }}
            >
              <Plus className="h-4 w-4" />
              Nuevo usuario
            </Button>
          )
        }
      />

      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <FilterTabs<Tab>
          value={tab}
          onChange={(v) => {
            setTab(v)
            setPage(1)
          }}
          loading={countsQ.isLoading}
          tabs={[
            { value: "todos", label: "Todos", count: countsQ.data?.todos ?? 0 },
            { value: "activos", label: "Activos", count: countsQ.data?.activos ?? 0 },
            { value: "inactivos", label: "Archivados", count: countsQ.data?.inactivos ?? 0 },
          ]}
        />

        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar nombre, correo o DNI"
            className="w-64 rounded-md border border-border bg-background py-1.5 pl-8 pr-3 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      </div>

      {archivar.isError && (
        <div className="mb-3">
          <FormError message={apiErrorMessage(archivar.error, "No se pudo archivar")} />
        </div>
      )}

      {isLoading ? (
        <SkeletonTable
          rows={6}
          headers={["Usuario", "Correo", "Rol", "Último acceso", "Estado", ""]}
          columns={["w-40", "w-52", "w-24", "w-28", "w-16", "w-16"]}
        />
      ) : (
        <div className={isFetching ? "opacity-60 transition-opacity" : "transition-opacity"}>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-secondary">
                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-2.5">Usuario</th>
                  <th className="px-4 py-2.5">Correo</th>
                  <th className="px-4 py-2.5">Rol</th>
                  <th className="px-4 py-2.5">Último acceso</th>
                  <th className="px-4 py-2.5">Estado</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {rows.map((u, i) => {
                  const esYo = u.id === meId
                  return (
                    <tr
                      key={u.id}
                      className={
                        i % 2 === 1 ? "border-t border-border bg-muted/30" : "border-t border-border"
                      }
                    >
                      <td className="px-4 py-2.5 font-medium">
                        {u.full_name}
                        {esYo && (
                          <span className="ml-2 text-xs font-normal text-muted-foreground">(tú)</span>
                        )}
                        {u.dni && <div className="text-xs text-muted-foreground">DNI {u.dni}</div>}
                      </td>
                      <td className="px-4 py-2.5 text-muted-foreground">{u.email}</td>
                      <td className="px-4 py-2.5">{u.role.name}</td>
                      <td className="tabular px-4 py-2.5 text-muted-foreground">
                        {fmtDate(u.last_login_at)}
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge tone={u.is_active ? "success" : "neutral"}>
                          {u.is_active ? "Activo" : "Archivado"}
                        </Badge>
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex justify-end gap-1">
                          {canEdit && (
                            <button
                              onClick={() => {
                                setEditando(u)
                                setFormOpen(true)
                              }}
                              className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                              title="Editar"
                              aria-label={`Editar ${u.full_name}`}
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                          )}
                          {/* La cuenta propia no se archiva ni se borra: el
                              backend lo rechaza y quedarías fuera del sistema. */}
                          {canEdit && !esYo && (
                            <button
                              onClick={() => archivar.mutate({ id: u.id, activo: !u.is_active })}
                              disabled={archivar.isPending}
                              className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                              title={
                                u.is_active
                                  ? "Archivar: deja de poder entrar, conserva su historial"
                                  : "Restaurar el acceso"
                              }
                              aria-label={`${u.is_active ? "Archivar" : "Restaurar"} ${u.full_name}`}
                            >
                              {u.is_active ? (
                                <Archive className="h-3.5 w-3.5" />
                              ) : (
                                <ArchiveRestore className="h-3.5 w-3.5" />
                              )}
                            </button>
                          )}
                          {canDelete && !esYo && (
                            <button
                              onClick={() => {
                                eliminar.reset()
                                setPorEliminar(u)
                              }}
                              className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-state-danger"
                              title="Eliminar definitivamente"
                              aria-label={`Eliminar ${u.full_name}`}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-10 text-center text-sm text-muted-foreground">
                      No hay usuarios que coincidan con el filtro.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <Paginacion
            page={page}
            pageSize={PAGE_SIZE}
            total={total}
            onChange={setPage}
            etiqueta="usuarios"
          />
        </div>
      )}

      <UsuarioFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        usuario={editando}
        esYo={editando?.id === meId}
      />

      <ConfirmarEliminar
        open={Boolean(porEliminar)}
        onClose={() => setPorEliminar(null)}
        titulo="Eliminar usuario definitivamente"
        subtitulo={porEliminar ? `${porEliminar.full_name} · ${porEliminar.email}` : undefined}
        error={eliminar.isError ? apiErrorMessage(eliminar.error, "No se pudo eliminar") : null}
        cargando={eliminar.isPending}
        onEliminar={() => porEliminar && eliminar.mutate(porEliminar.id)}
        onArchivar={
          porEliminar?.is_active
            ? () => {
                archivar.mutate({ id: porEliminar.id, activo: false })
                setPorEliminar(null)
              }
            : undefined
        }
      >
        Se borra la cuenta y no se puede deshacer. Si ya trabajó —fichas, ventas, kardex, caja o
        auditoría— el sistema lo impedirá: en ese caso{" "}
        <strong className="text-foreground">archívala</strong>, así deja de poder entrar pero sus
        documentos siguen diciendo quién los hizo.
      </ConfirmarEliminar>
    </div>
  )
}
