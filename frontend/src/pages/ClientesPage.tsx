import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { Archive, ArchiveRestore, Bike, Pencil, Plus, Search, Trash2 } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { usePermission } from "@/lib/auth"
import { Badge } from "@/components/ui/Badge"
import { ConfirmarEliminar } from "@/components/ui/ConfirmarEliminar"
import { Button, FormError } from "@/components/ui/Form"
import { FilterTabs } from "@/components/ui/FilterTabs"
import { PageHeader } from "@/components/ui/PageHeader"
import { Paginacion } from "@/components/ui/Paginacion"
import { SkeletonTable } from "@/components/ui/skeleton"
import { ClienteFormModal } from "@/features/clientes/ClienteFormModal"
import { fmtFecha, type Cliente, type Page } from "@/features/clientes/types"

type Tab = "todos" | "activos" | "inactivos"
const PAGE_SIZE = 25

export default function ClientesPage() {
  const canCreate = usePermission("clientes.crear")
  const canEdit = usePermission("clientes.editar")
  const canDelete = usePermission("clientes.eliminar")

  const [tab, setTab] = useState<Tab>("activos")
  const [search, setSearch] = useState("")
  const [debounced, setDebounced] = useState("")
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState<Cliente | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [porEliminar, setPorEliminar] = useState<Cliente | null>(null)

  const qc = useQueryClient()
  const refrescar = () => qc.invalidateQueries({ queryKey: ["clientes"] })

  const archivar = useMutation({
    mutationFn: async ({ id, activo }: { id: string; activo: boolean }) => {
      await api.patch(`${API_PREFIX}/clientes/${id}`, { is_active: activo })
    },
    // Archivar un cliente archiva sus bicicletas, así que la lista de bicis
    // que hubiera en caché también queda vieja.
    onSuccess: () => {
      refrescar()
      qc.invalidateQueries({ queryKey: ["bicicletas"] })
    },
  })

  const eliminar = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`${API_PREFIX}/clientes/${id}`)
    },
    onSuccess: () => {
      refrescar()
      qc.invalidateQueries({ queryKey: ["bicicletas"] })
      setPorEliminar(null)
    },
  })

  // Debounce: la búsqueda va al servidor, no filtramos en cliente porque
  // la lista está paginada y sólo tenemos la página actual.
  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search)
      setPage(1)
    }, 300)
    return () => clearTimeout(t)
  }, [search])

  const activeFilter = tab === "todos" ? undefined : tab === "activos"

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["clientes", { tab, debounced, page }],
    queryFn: async () =>
      (
        await api.get<Page<Cliente>>(`${API_PREFIX}/clientes`, {
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
  const counts = useQuery({
    queryKey: ["clientes", "counts", debounced],
    queryFn: async () => {
      const params = { search: debounced || undefined, page_size: 1 }
      const [todos, activos, inactivos] = await Promise.all([
        api.get<Page<Cliente>>(`${API_PREFIX}/clientes`, { params }),
        api.get<Page<Cliente>>(`${API_PREFIX}/clientes`, {
          params: { ...params, is_active: true },
        }),
        api.get<Page<Cliente>>(`${API_PREFIX}/clientes`, {
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

  const items = data?.items ?? []
  const total = data?.total ?? 0

  const openNuevo = () => {
    setEditing(null)
    setModalOpen(true)
  }
  const openEditar = (c: Cliente) => {
    setEditing(c)
    setModalOpen(true)
  }

  return (
    <div>
      <PageHeader
        title="Clientes"
        description="Directorio de clientes de la tienda y el taller."
        actions={
          canCreate && (
            <Button onClick={openNuevo}>
              <Plus className="h-4 w-4" />
              Nuevo cliente
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
          loading={counts.isLoading}
          tabs={[
            { value: "todos", label: "Todos", count: counts.data?.todos ?? 0 },
            { value: "activos", label: "Activos", count: counts.data?.activos ?? 0 },
            { value: "inactivos", label: "Archivados", count: counts.data?.inactivos ?? 0 },
          ]}
        />

        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar nombre, documento, teléfono..."
            className="w-72 rounded-md border border-border bg-background py-1.5 pl-8 pr-3 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
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
          rows={8}
          headers={["Cliente", "Documento", "Contacto", "Bicicletas", "Registro", "Estado", ""]}
          columns={["w-44", "w-28", "w-32", "w-16", "w-24", "w-16", "w-8"]}
        />
      ) : (
        <div className={isFetching ? "opacity-60 transition-opacity" : "transition-opacity"}>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-secondary">
                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-2.5">Cliente</th>
                  <th className="px-4 py-2.5">Documento</th>
                  <th className="px-4 py-2.5">Contacto</th>
                  <th className="px-4 py-2.5">Bicicletas</th>
                  <th className="px-4 py-2.5">Registro</th>
                  <th className="px-4 py-2.5">Estado</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {items.map((c, i) => (
                  <tr
                    key={c.id}
                    className={
                      i % 2 === 1
                        ? "border-t border-border bg-muted/30"
                        : "border-t border-border"
                    }
                  >
                    <td className="px-4 py-2.5">
                      <Link
                        to={`/clientes/${c.id}`}
                        className="font-medium hover:text-primary hover:underline"
                      >
                        {c.nombre}
                      </Link>
                      {c.direccion && (
                        <div className="text-xs text-muted-foreground">{c.direccion}</div>
                      )}
                    </td>
                    <td className="tabular px-4 py-2.5">
                      <span className="text-muted-foreground">{c.tipo_documento}</span>{" "}
                      {c.numero_documento}
                    </td>
                    <td className="px-4 py-2.5 text-muted-foreground">
                      {c.telefono && <div className="tabular">{c.telefono}</div>}
                      {c.email && <div className="text-xs">{c.email}</div>}
                      {!c.telefono && !c.email && "—"}
                    </td>
                    <td className="tabular px-4 py-2.5">
                      <span className="inline-flex items-center gap-1.5 text-muted-foreground">
                        <Bike className="h-3.5 w-3.5" />
                        {c.bicicletas_count}
                      </span>
                    </td>
                    <td className="tabular px-4 py-2.5 text-muted-foreground">
                      {fmtFecha(c.created_at)}
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge tone={c.is_active ? "success" : "neutral"}>
                        {c.is_active ? "Activo" : "Archivado"}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex justify-end gap-1">
                        {canEdit && (
                          <button
                            onClick={() => openEditar(c)}
                            className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                            title="Editar"
                            aria-label={`Editar ${c.nombre}`}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                        )}
                        {canEdit && (
                          <button
                            onClick={() => archivar.mutate({ id: c.id, activo: !c.is_active })}
                            disabled={archivar.isPending}
                            className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                            title={
                              c.is_active
                                ? "Archivar: sale del directorio junto con sus bicicletas, pero conserva su historial"
                                : "Restaurar al directorio"
                            }
                            aria-label={`${c.is_active ? "Archivar" : "Restaurar"} ${c.nombre}`}
                          >
                            {c.is_active ? (
                              <Archive className="h-3.5 w-3.5" />
                            ) : (
                              <ArchiveRestore className="h-3.5 w-3.5" />
                            )}
                          </button>
                        )}
                        {canDelete && (
                          <button
                            onClick={() => {
                              eliminar.reset()
                              setPorEliminar(c)
                            }}
                            className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-state-danger"
                            title="Eliminar definitivamente"
                            aria-label={`Eliminar ${c.nombre}`}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {items.length === 0 && (
                  <tr>
                    <td
                      colSpan={7}
                      className="px-4 py-12 text-center text-sm text-muted-foreground"
                    >
                      {debounced
                        ? `Sin resultados para "${debounced}".`
                        : "Aún no hay clientes registrados."}
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
            etiqueta="clientes"
          />
        </div>
      )}

      <ClienteFormModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        cliente={editing}
      />

      <ConfirmarEliminar
        open={Boolean(porEliminar)}
        onClose={() => setPorEliminar(null)}
        titulo="Eliminar cliente definitivamente"
        subtitulo={
          porEliminar
            ? `${porEliminar.nombre} · ${porEliminar.tipo_documento} ${porEliminar.numero_documento}`
            : undefined
        }
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
        Se borra el cliente
        {porEliminar && porEliminar.bicicletas_count > 0 && (
          <>
            {" "}
            y sus <strong className="text-foreground">
              {porEliminar.bicicletas_count} bicicleta(s)
            </strong>
          </>
        )}
        , y no se puede deshacer. Si tiene fichas o ventas a su nombre, el sistema lo
        impedirá: en ese caso <strong className="text-foreground">archívalo</strong>, así sale
        del directorio pero sus documentos siguen cuadrando.
      </ConfirmarEliminar>
    </div>
  )
}
