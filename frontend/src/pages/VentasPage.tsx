import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import {
  Archive,
  ArchiveRestore,
  FileDown,
  FileText,
  Plus,
  Printer,
  Search,
  ShoppingCart,
} from "lucide-react"

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
  ESTADOS_VENTA,
  ESTADO_VENTA_INFO,
  soles,
  type ConteoVentas,
  type EstadoVenta,
  type TipoVenta,
  type Venta,
} from "@/features/ventas/types"

const PAGE_SIZE = 25
// "ARCHIVADAS" no es un estado: es el archivo, fuera del listado de trabajo.
type Tab = "TODAS" | "ARCHIVADAS" | EstadoVenta

//: Una cotización viva sigue en juego; el resto ya no se toca.
const ESTADOS_ARCHIVABLES = new Set(["CONFIRMADA", "ANULADA", "RECHAZADA"])

export default function VentasPage({ tipo }: { tipo: TipoVenta }) {
  const canCreate = usePermission("ventas.crear")
  const canEdit = usePermission("ventas.editar")
  const esCotizacion = tipo === "COTIZACION"

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

  // Reinicia la pestaña al cambiar entre Ventas y Cotizaciones: los estados
  // relevantes no son los mismos.
  useEffect(() => {
    setTab("TODAS")
    setPage(1)
  }, [tipo])

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["ventas", tipo, { tab, debounced, page }],
    queryFn: async () =>
      (
        await api.get<Page<Venta>>(`${API_PREFIX}/ventas`, {
          params: {
            tipo,
            estado: tab === "TODAS" || tab === "ARCHIVADAS" ? undefined : tab,
            archivadas: tab === "ARCHIVADAS" || undefined,
            search: debounced || undefined,
            page,
            page_size: PAGE_SIZE,
          },
        })
      ).data,
    placeholderData: (prev) => prev,
  })

  const conteos = useQuery({
    queryKey: ["ventas", tipo, "conteos"],
    queryFn: async () =>
      (await api.get<ConteoVentas>(`${API_PREFIX}/ventas/conteos`, { params: { tipo } })).data,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0

  // El PDF se pide con el cliente autenticado (el navegador no manda la
  // cabecera Authorization en una navegación normal) y se abre como blob.
  const abrirPdf = async (v: Venta, formato: "pdf" | "ticket") => {
    const res = await api.get(`${API_PREFIX}/ventas/${v.id}/${formato}`, {
      responseType: "blob",
    })
    const url = URL.createObjectURL(res.data as Blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${formato === "ticket" ? "ticket" : esCotizacion ? "cotizacion" : "venta"}-${v.numero}.pdf`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  }

  const qc = useQueryClient()
  const archivar = useMutation({
    mutationFn: async ({ id, archivar: hacia }: { id: string; archivar: boolean }) => {
      await api.post(`${API_PREFIX}/ventas/${id}/${hacia ? "archivar" : "restaurar"}`)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ventas"] }),
  })

  // Las cotizaciones no llegan a Anulada; las ventas no usan Pendiente/Rechazada.
  const estadosVisibles = esCotizacion
    ? (["PENDIENTE", "CONFIRMADA", "RECHAZADA"] as EstadoVenta[])
    : (["CONFIRMADA", "ANULADA"] as EstadoVenta[])

  return (
    <div>
      <PageHeader
        title={esCotizacion ? "Cotizaciones" : "Ventas"}
        description={
          esCotizacion
            ? "Proformas emitidas. Al aceptarlas se convierten en venta."
            : "Comprobantes de venta del mostrador y el taller."
        }
        actions={
          canCreate && (
            <Link to="/ventas/nueva">
              <Button>
                <Plus className="h-4 w-4" />
                {esCotizacion ? "Nueva cotización" : "Nueva venta"}
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
            ...ESTADOS_VENTA.filter((e) => estadosVisibles.includes(e.value)).map((e) => ({
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
            placeholder="N° de documento o cliente..."
            className="w-64 rounded-md border border-border bg-background py-1.5 pl-8 pr-3 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      </div>

      {isLoading ? (
        <SkeletonTable
          rows={8}
          headers={["N°", "Cliente", "Fecha", "Total", "Estado", ""]}
          columns={["w-24", "w-40", "w-24", "w-24", "w-28", "w-10"]}
        />
      ) : (
        <div className={isFetching ? "opacity-60 transition-opacity" : "transition-opacity"}>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-secondary">
                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-2.5">N°</th>
                  <th className="px-4 py-2.5">Cliente</th>
                  <th className="px-4 py-2.5">Fecha</th>
                  <th className="px-4 py-2.5 text-right">Total</th>
                  <th className="px-4 py-2.5">Estado</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {items.map((v, i) => (
                  <tr
                    key={v.id}
                    className={
                      i % 2 === 1 ? "border-t border-border bg-muted/30" : "border-t border-border"
                    }
                  >
                    <td className="px-4 py-2.5">
                      <Link
                        to={`/ventas/${v.id}`}
                        className="tabular font-semibold hover:text-primary hover:underline"
                      >
                        {v.numero}
                      </Link>
                    </td>
                    <td className="px-4 py-2.5">
                      {v.cliente ? (
                        v.cliente.nombre
                      ) : (
                        <span className="text-muted-foreground">Público general</span>
                      )}
                    </td>
                    <td className="tabular px-4 py-2.5 text-muted-foreground">
                      {fmtFecha(v.created_at)}
                    </td>
                    <td className="tabular px-4 py-2.5 text-right font-medium">{soles(v.total)}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1.5">
                        <Badge tone={ESTADO_VENTA_INFO[v.estado].tone}>
                          {ESTADO_VENTA_INFO[v.estado].label}
                        </Badge>
                        {v.vencida && <Badge tone="danger">Vencida</Badge>}
                      </div>
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex justify-end gap-1">
                        <Link
                          to={`/ventas/${v.id}`}
                          className="inline-flex rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                          aria-label="Ver documento"
                        >
                          <FileText className="h-3.5 w-3.5" />
                        </Link>
                        <button
                          onClick={() => abrirPdf(v, "pdf")}
                          className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                          title="Descargar en A4"
                          aria-label={`Descargar ${v.numero} en A4`}
                        >
                          <FileDown className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={() => abrirPdf(v, "ticket")}
                          className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                          title="Descargar en ticket de 80 mm"
                          aria-label={`Descargar ${v.numero} en ticket de 80 mm`}
                        >
                          <Printer className="h-3.5 w-3.5" />
                        </button>
                        {/* Archivar no anula ni borra: el documento sigue en
                            caja, kardex, reportes y ante SUNAT. */}
                        {canEdit && (v.archivada || ESTADOS_ARCHIVABLES.has(v.estado)) && (
                          <button
                            onClick={() => archivar.mutate({ id: v.id, archivar: !v.archivada })}
                            disabled={archivar.isPending}
                            className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                            title={
                              v.archivada
                                ? "Restaurar al listado"
                                : "Archivar: sale del listado, sigue contando en caja y reportes"
                            }
                            aria-label={`${v.archivada ? "Restaurar" : "Archivar"} ${v.numero}`}
                          >
                            {v.archivada ? (
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
                    <td colSpan={6} className="px-4 py-14 text-center text-sm text-muted-foreground">
                      <ShoppingCart className="mx-auto h-8 w-8 text-muted-foreground/50" />
                      <p className="mt-2">
                        {debounced
                          ? `Sin resultados para "${debounced}".`
                          : esCotizacion
                            ? "Aún no hay cotizaciones."
                            : "Aún no hay ventas registradas."}
                      </p>
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
            etiqueta="documentos"
          />
        </div>
      )}
    </div>
  )
}
