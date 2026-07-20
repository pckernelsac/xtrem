import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { Archive, ArchiveRestore, Pencil, Plus, Search, Trash2 } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { usePermission } from "@/lib/auth"
import { Badge } from "@/components/ui/Badge"
import { ConfirmarEliminar } from "@/components/ui/ConfirmarEliminar"
import { Button, FormError } from "@/components/ui/Form"
import { FilterTabs } from "@/components/ui/FilterTabs"
import { PageHeader } from "@/components/ui/PageHeader"
import { Paginacion } from "@/components/ui/Paginacion"
import { SkeletonTable } from "@/components/ui/skeleton"
import { BicicletaFormModal } from "@/features/clientes/BicicletaFormModal"
import { fmtFecha, type Bicicleta, type Page } from "@/features/clientes/types"

type Tab = "todas" | "activas" | "inactivas"
const PAGE_SIZE = 25

export default function BicicletasPage() {
  const canCreate = usePermission("bicicletas.crear")
  const canEdit = usePermission("bicicletas.editar")
  const canDelete = usePermission("bicicletas.eliminar")

  const [tab, setTab] = useState<Tab>("activas")
  const [search, setSearch] = useState("")
  const [debounced, setDebounced] = useState("")
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState<Bicicleta | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [porEliminar, setPorEliminar] = useState<Bicicleta | null>(null)

  const qc = useQueryClient()
  // También se invalida clientes: su tarjeta muestra el conteo de bicicletas.
  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ["bicicletas"] })
    qc.invalidateQueries({ queryKey: ["clientes"] })
  }

  const archivar = useMutation({
    mutationFn: async ({ id, activo }: { id: string; activo: boolean }) => {
      await api.patch(`${API_PREFIX}/bicicletas/${id}`, { is_active: activo })
    },
    onSuccess: refrescar,
  })

  const eliminar = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`${API_PREFIX}/bicicletas/${id}`)
    },
    onSuccess: () => {
      refrescar()
      setPorEliminar(null)
    },
  })

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search)
      setPage(1)
    }, 300)
    return () => clearTimeout(t)
  }, [search])

  const activeFilter = tab === "todas" ? undefined : tab === "activas"

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["bicicletas", { tab, debounced, page }],
    queryFn: async () =>
      (
        await api.get<Page<Bicicleta>>(`${API_PREFIX}/bicicletas`, {
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

  const counts = useQuery({
    queryKey: ["bicicletas", "counts", debounced],
    queryFn: async () => {
      const params = { search: debounced || undefined, page_size: 1 }
      const [todas, activas, inactivas] = await Promise.all([
        api.get<Page<Bicicleta>>(`${API_PREFIX}/bicicletas`, { params }),
        api.get<Page<Bicicleta>>(`${API_PREFIX}/bicicletas`, {
          params: { ...params, is_active: true },
        }),
        api.get<Page<Bicicleta>>(`${API_PREFIX}/bicicletas`, {
          params: { ...params, is_active: false },
        }),
      ])
      return {
        todas: todas.data.total,
        activas: activas.data.total,
        inactivas: inactivas.data.total,
      }
    },
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div>
      <PageHeader
        title="Bicicletas"
        description="Todas las bicicletas registradas y su dueño actual."
        actions={
          canCreate && (
            <Button
              onClick={() => {
                setEditing(null)
                setModalOpen(true)
              }}
            >
              <Plus className="h-4 w-4" />
              Nueva bicicleta
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
            { value: "todas", label: "Todas", count: counts.data?.todas ?? 0 },
            { value: "activas", label: "Activas", count: counts.data?.activas ?? 0 },
            { value: "inactivas", label: "Archivadas", count: counts.data?.inactivas ?? 0 },
          ]}
        />

        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar marca, serie o cliente..."
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
          headers={["Bicicleta", "Tipo", "N° Serie", "Dueño", "Registro", "Estado", ""]}
          columns={["w-44", "w-20", "w-28", "w-40", "w-24", "w-16", "w-8"]}
        />
      ) : (
        <div className={isFetching ? "opacity-60 transition-opacity" : "transition-opacity"}>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-secondary">
                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-2.5">Bicicleta</th>
                  <th className="px-4 py-2.5">Tipo</th>
                  <th className="px-4 py-2.5">N° Serie</th>
                  <th className="px-4 py-2.5">Dueño</th>
                  <th className="px-4 py-2.5">Registro</th>
                  <th className="px-4 py-2.5">Estado</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {items.map((b, i) => (
                  <tr
                    key={b.id}
                    className={
                      i % 2 === 1 ? "border-t border-border bg-muted/30" : "border-t border-border"
                    }
                  >
                    <td className="px-4 py-2.5">
                      <Link
                        to={`/bicicletas/${b.id}`}
                        className="font-medium hover:text-primary hover:underline"
                      >
                        {b.descripcion}
                      </Link>
                      {(b.rodado || b.talla || b.anio) && (
                        <div className="tabular text-xs text-muted-foreground">
                          {[
                            b.rodado && `R${b.rodado}`,
                            b.talla && `Talla ${b.talla}`,
                            b.anio,
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-muted-foreground">{b.tipo}</td>
                    <td className="tabular px-4 py-2.5 text-muted-foreground">
                      {b.numero_serie || "—"}
                    </td>
                    <td className="px-4 py-2.5">
                      <Link
                        to={`/clientes/${b.cliente_id}`}
                        className="hover:text-primary hover:underline"
                      >
                        {b.cliente.nombre}
                      </Link>
                      <div className="tabular text-xs text-muted-foreground">
                        {b.cliente.tipo_documento} {b.cliente.numero_documento}
                      </div>
                    </td>
                    <td className="tabular px-4 py-2.5 text-muted-foreground">
                      {fmtFecha(b.created_at)}
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge tone={b.is_active ? "success" : "neutral"}>
                        {b.is_active ? "Activa" : "Archivada"}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex justify-end gap-1">
                        {canEdit && (
                          <button
                            onClick={() => {
                              setEditing(b)
                              setModalOpen(true)
                            }}
                            className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                            title="Editar"
                            aria-label={`Editar ${b.descripcion}`}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                        )}
                        {canEdit && (
                          <button
                            onClick={() => archivar.mutate({ id: b.id, activo: !b.is_active })}
                            disabled={archivar.isPending}
                            className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                            title={
                              b.is_active
                                ? "Archivar: sale del listado pero conserva su historial de fichas"
                                : "Restaurar al listado"
                            }
                            aria-label={`${b.is_active ? "Archivar" : "Restaurar"} ${b.descripcion}`}
                          >
                            {b.is_active ? (
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
                              setPorEliminar(b)
                            }}
                            className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-state-danger"
                            title="Eliminar definitivamente"
                            aria-label={`Eliminar ${b.descripcion}`}
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
                    <td colSpan={7} className="px-4 py-12 text-center text-sm text-muted-foreground">
                      {debounced
                        ? `Sin resultados para "${debounced}".`
                        : "Aún no hay bicicletas registradas."}
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
            etiqueta="bicicletas"
          />
        </div>
      )}

      <BicicletaFormModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        bicicleta={editing}
      />

      <ConfirmarEliminar
        open={Boolean(porEliminar)}
        onClose={() => setPorEliminar(null)}
        titulo="Eliminar bicicleta definitivamente"
        subtitulo={
          porEliminar ? `${porEliminar.descripcion} · ${porEliminar.cliente.nombre}` : undefined
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
        Se borra la bicicleta y no se puede deshacer. Si tiene fichas de taller, el sistema lo
        impedirá: en ese caso <strong className="text-foreground">archívala</strong>, así sale
        del listado pero su historial se conserva.
      </ConfirmarEliminar>
    </div>
  )
}
