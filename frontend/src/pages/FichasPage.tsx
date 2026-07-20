import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { Archive, ArchiveRestore, FileText, PenLine, Plus, Search } from "lucide-react"

import { api, API_PREFIX } from "@/lib/api"
import { usePermission } from "@/lib/auth"
import { Badge } from "@/components/ui/Badge"
import { Button } from "@/components/ui/Form"
import { FilterTabs } from "@/components/ui/FilterTabs"
import { PageHeader } from "@/components/ui/PageHeader"
import { Paginacion } from "@/components/ui/Paginacion"
import { SkeletonTable } from "@/components/ui/skeleton"
import { fmtFecha, type Page } from "@/features/clientes/types"
import {
  ESTADOS,
  ESTADO_INFO,
  soles,
  type Conteos,
  type EstadoFicha,
  type Ficha,
} from "@/features/fichas/types"

const PAGE_SIZE = 25
// "ARCHIVADAS" no es un estado: es el archivo, que vive fuera del tablero.
type Tab = "TODAS" | "ARCHIVADAS" | EstadoFicha

const ESTADOS_ARCHIVABLES = new Set(["ENTREGADA", "CANCELADA"])

export default function FichasPage() {
  const canCreate = usePermission("fichas.crear")
  const canEdit = usePermission("fichas.editar")

  const [tab, setTab] = useState<Tab>("TODAS")
  const [search, setSearch] = useState("")
  const [debounced, setDebounced] = useState("")
  const [page, setPage] = useState(1)

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search)
      setPage(1)
    }, 300)
    return () => clearTimeout(t)
  }, [search])

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["fichas", { tab, debounced, page }],
    queryFn: async () =>
      (
        await api.get<Page<Ficha>>(`${API_PREFIX}/fichas`, {
          params: {
            search: debounced || undefined,
            estado: tab === "TODAS" || tab === "ARCHIVADAS" ? undefined : tab,
            archivadas: tab === "ARCHIVADAS" || undefined,
            page,
            page_size: PAGE_SIZE,
          },
        })
      ).data,
    placeholderData: (prev) => prev,
  })

  // Un solo endpoint devuelve todos los contadores: evita disparar
  // una consulta por pestaña como en Clientes.
  const conteos = useQuery({
    queryKey: ["fichas", "conteos", debounced],
    queryFn: async () =>
      (
        await api.get<Conteos>(`${API_PREFIX}/fichas/conteos`, {
          params: { search: debounced || undefined },
        })
      ).data,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0

  const qc = useQueryClient()
  const archivar = useMutation({
    mutationFn: async ({ id, archivar: hacia }: { id: string; archivar: boolean }) => {
      await api.post(`${API_PREFIX}/fichas/${id}/${hacia ? "archivar" : "restaurar"}`)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["fichas"] }),
  })

  return (
    <div>
      <PageHeader
        title="Fichas de mantenimiento"
        description="Órdenes de trabajo del taller, desde la recepción hasta la entrega."
        actions={
          canCreate && (
            <Link to="/fichas/nueva">
              <Button>
                <Plus className="h-4 w-4" />
                Nueva ficha
              </Button>
            </Link>
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
          loading={conteos.isLoading}
          tabs={[
            { value: "TODAS", label: "Todas", count: conteos.data?.todas ?? 0 },
            ...ESTADOS.map((e) => ({
              value: e.value as Tab,
              label: e.label,
              count: conteos.data?.por_estado[e.value] ?? 0,
            })),
            {
              value: "ARCHIVADAS" as Tab,
              label: "Archivadas",
              count: conteos.data?.archivadas ?? 0,
            },
          ]}
        />

        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="N° de ficha, cliente o bicicleta..."
            className="w-72 rounded-md border border-border bg-background py-1.5 pl-8 pr-3 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      </div>

      {isLoading ? (
        <SkeletonTable
          rows={8}
          headers={["N° Ficha", "Cliente", "Bicicleta", "Recepción", "Total", "Estado", ""]}
          columns={["w-20", "w-40", "w-36", "w-24", "w-20", "w-28", "w-10"]}
        />
      ) : (
        <div className={isFetching ? "opacity-60 transition-opacity" : "transition-opacity"}>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-secondary">
                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-2.5">N° Ficha</th>
                  <th className="px-4 py-2.5">Cliente</th>
                  <th className="px-4 py-2.5">Bicicleta</th>
                  <th className="px-4 py-2.5">Recepción</th>
                  <th className="px-4 py-2.5 text-right">Repuestos</th>
                  <th className="px-4 py-2.5">Estado</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {items.map((f, i) => (
                  <tr
                    key={f.id}
                    className={
                      i % 2 === 1 ? "border-t border-border bg-muted/30" : "border-t border-border"
                    }
                  >
                    <td className="px-4 py-2.5">
                      <Link
                        to={`/fichas/${f.id}`}
                        className="tabular font-semibold hover:text-primary hover:underline"
                      >
                        {f.numero}
                      </Link>
                    </td>
                    <td className="px-4 py-2.5">
                      <Link
                        to={`/clientes/${f.cliente.id}`}
                        className="hover:text-primary hover:underline"
                      >
                        {f.cliente.nombre}
                      </Link>
                      <div className="tabular text-xs text-muted-foreground">
                        {f.cliente.tipo_documento} {f.cliente.numero_documento}
                      </div>
                    </td>
                    <td className="px-4 py-2.5">
                      <Link
                        to={`/bicicletas/${f.bicicleta.id}`}
                        className="hover:text-primary hover:underline"
                      >
                        {[f.bicicleta.marca, f.bicicleta.modelo].filter(Boolean).join(" ")}
                      </Link>
                      {f.bicicleta.numero_serie && (
                        <div className="tabular text-xs text-muted-foreground">
                          {f.bicicleta.numero_serie}
                        </div>
                      )}
                    </td>
                    <td className="tabular px-4 py-2.5 text-muted-foreground">
                      {fmtFecha(f.fecha_recepcion)}
                    </td>
                    <td className="tabular px-4 py-2.5 text-right">{soles(f.total_repuestos)}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1.5">
                        <Badge tone={ESTADO_INFO[f.estado].tone}>
                          {ESTADO_INFO[f.estado].label}
                        </Badge>
                        {f.esta_firmada && (
                          <span title="Firmada por cliente y técnico">
                            <PenLine className="h-3.5 w-3.5 text-state-success" />
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex justify-end gap-1">
                        <Link
                          to={`/fichas/${f.id}`}
                          title="Abrir la ficha"
                          className="inline-flex rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                        >
                          <FileText className="h-3.5 w-3.5" />
                        </Link>
                        {/* Sólo lo cerrado sale del tablero: una ficha en curso
                            archivada es trabajo que se pierde de vista. */}
                        {canEdit && (f.archivada || ESTADOS_ARCHIVABLES.has(f.estado)) && (
                          <button
                            onClick={() =>
                              archivar.mutate({ id: f.id, archivar: !f.archivada })
                            }
                            disabled={archivar.isPending}
                            className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                            title={
                              f.archivada
                                ? "Restaurar al tablero"
                                : "Archivar: sale del tablero, el historial de la bici no cambia"
                            }
                            aria-label={`${f.archivada ? "Restaurar" : "Archivar"} ficha ${f.numero}`}
                          >
                            {f.archivada ? (
                              <ArchiveRestore className="h-3.5 w-3.5" />
                            ) : (
                              <Archive className="h-3.5 w-3.5" />
                            )}
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
                        : tab === "ARCHIVADAS"
                          ? "No hay fichas archivadas."
                          : "Aún no hay fichas registradas."}
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
            etiqueta="fichas"
          />
        </div>
      )}
    </div>
  )
}
