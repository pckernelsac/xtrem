import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import {
  AlertTriangle,
  FileCode2,
  FileSpreadsheet,
  FileText,
  MessageCircle,
  Receipt,
  Search,
} from "lucide-react"

import { api, API_PREFIX } from "@/lib/api"
import { Badge } from "@/components/ui/Badge"
import { Button } from "@/components/ui/Form"
import { CompartirComprobanteModal } from "@/features/facturacion/CompartirComprobanteModal"
import { ExportarContadorModal } from "@/features/facturacion/ExportarContadorModal"
import { FilterTabs } from "@/components/ui/FilterTabs"
import { PageHeader } from "@/components/ui/PageHeader"
import { Paginacion } from "@/components/ui/Paginacion"
import { SkeletonTable } from "@/components/ui/skeleton"
import { fmtFecha, type Page } from "@/features/clientes/types"
import {
  ESTADOS_COMPROBANTE,
  ESTADO_COMP_INFO,
  TIPO_COMP_LABEL,
  type Comprobante,
  type ConteoComprobantes,
  type EstadoComprobante,
} from "@/features/facturacion/types"

const PAGE_SIZE = 25
type Tab = "TODAS" | EstadoComprobante

/** Enlace a un archivo del comprobante (XML/PDF/CDR), estilo FactPro. */
function ArchivoLink({
  url,
  label,
  icon: Icon,
}: {
  url: string | null
  label: string
  icon: typeof FileText
}) {
  if (!url) {
    return <span className="text-xs text-muted-foreground/40">{label}</span>
  }
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
      title={`Abrir ${label}`}
    >
      <Icon className="h-3 w-3" />
      {label}
    </a>
  )
}

export default function DocumentosPage() {
  const [tab, setTab] = useState<Tab>("TODAS")
  const [search, setSearch] = useState("")
  const [debounced, setDebounced] = useState("")
  const [page, setPage] = useState(1)
  const [exportOpen, setExportOpen] = useState(false)
  const [compartir, setCompartir] = useState<Comprobante | null>(null)

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search)
      setPage(1)
    }, 300)
    return () => clearTimeout(t)
  }, [search])

  const conteos = useQuery({
    queryKey: ["facturacion", "conteos"],
    queryFn: async () =>
      (await api.get<ConteoComprobantes>(`${API_PREFIX}/facturacion/conteos`)).data,
  })

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["facturacion", "documentos", { tab, debounced, page }],
    queryFn: async () =>
      (
        await api.get<Page<Comprobante>>(`${API_PREFIX}/facturacion/documentos`, {
          params: {
            estado: tab === "TODAS" ? undefined : tab,
            search: debounced || undefined,
            page,
            page_size: PAGE_SIZE,
          },
        })
      ).data,
    placeholderData: (prev) => prev,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div>
      <PageHeader
        title="Documentos electrónicos"
        description="Comprobantes emitidos a SUNAT vía FactPro."
        actions={
          <Button variant="secondary" onClick={() => setExportOpen(true)}>
            <FileSpreadsheet className="h-4 w-4" />
            Excel para el contador
          </Button>
        }
      />

      <ExportarContadorModal open={exportOpen} onClose={() => setExportOpen(false)} />

      {conteos.data?.modo_simulacion && (
        <div className="mb-4 flex items-start gap-2 rounded-md border border-state-warning/40 bg-state-warning/10 px-4 py-3 text-sm text-state-warning">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-medium">Modo simulación</p>
            <p className="text-xs">
              No hay token de FactPro configurado. Los comprobantes se generan con la estructura
              real pero <strong>no se envían a SUNAT ni tienen validez tributaria</strong>. Configura{" "}
              <code className="rounded bg-black/10 px-1">FACTPRO_TOKEN</code> para emitir de verdad.
            </p>
          </div>
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <FilterTabs<Tab>
          value={tab}
          onChange={(v) => {
            setTab(v)
            setPage(1)
          }}
          loading={conteos.isLoading}
          tabs={[
            { value: "TODAS", label: "Todos", count: conteos.data?.todas ?? 0 },
            ...ESTADOS_COMPROBANTE.filter(
              (e) => (conteos.data?.por_estado[e.value] ?? 0) > 0 || e.value === "ACEPTADO",
            ).map((e) => ({
              value: e.value as Tab,
              label: e.label,
              count: conteos.data?.por_estado[e.value] ?? 0,
            })),
          ]}
        />

        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Serie-número o receptor..."
            className="w-64 rounded-md border border-border bg-background py-1.5 pl-8 pr-3 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      </div>

      {isLoading ? (
        <SkeletonTable
          rows={8}
          headers={["Documento", "Tipo", "Receptor", "Fecha", "Total", "Estado SUNAT", "Archivos"]}
          columns={["w-28", "w-20", "w-44", "w-24", "w-20", "w-28", "w-32"]}
        />
      ) : (
        <div className={isFetching ? "opacity-60 transition-opacity" : "transition-opacity"}>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-secondary">
                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-2.5">Documento</th>
                  <th className="px-4 py-2.5">Tipo</th>
                  <th className="px-4 py-2.5">Receptor</th>
                  <th className="px-4 py-2.5">Fecha</th>
                  <th className="px-4 py-2.5 text-right">Total</th>
                  <th className="px-4 py-2.5">Estado SUNAT</th>
                  <th className="px-4 py-2.5">Archivos</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {items.map((d, i) => (
                  <tr
                    key={d.id}
                    className={
                      i % 2 === 1 ? "border-t border-border bg-muted/30" : "border-t border-border"
                    }
                  >
                    <td className="px-4 py-2.5">
                      <Link
                        to={`/documentos/${d.id}`}
                        className="tabular font-semibold hover:text-primary hover:underline"
                      >
                        {d.numero_completo}
                      </Link>
                      {d.es_simulado && (
                        <div className="text-[10px] font-medium uppercase text-state-warning">
                          simulado
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-muted-foreground">
                      {TIPO_COMP_LABEL[d.tipo]}
                    </td>
                    <td className="px-4 py-2.5">
                      {d.cliente_denominacion}
                      <div className="tabular text-xs text-muted-foreground">
                        {d.cliente_numero_documento}
                      </div>
                    </td>
                    <td className="tabular px-4 py-2.5 text-muted-foreground">
                      {fmtFecha(d.fecha_emision)}
                    </td>
                    <td className="tabular px-4 py-2.5 text-right">
                      {d.total === null ? (
                        <span
                          className="text-muted-foreground"
                          title="Importe no disponible: se emitió antes de congelarlo y su venta ya no existe"
                        >
                          —
                        </span>
                      ) : (
                        `S/ ${Number(d.total).toLocaleString("es-PE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge tone={ESTADO_COMP_INFO[d.estado].tone}>
                        {d.descripcion_estado_sunat ?? ESTADO_COMP_INFO[d.estado].label}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-3">
                        <ArchivoLink url={d.xml_url} label="XML" icon={FileCode2} />
                        <ArchivoLink url={d.pdf_url} label="PDF" icon={FileText} />
                        <ArchivoLink url={d.cdr_url} label="CDR" icon={Receipt} />
                      </div>
                    </td>
                    <td className="px-4 py-2.5">
                      {d.pdf_url && (
                        <button
                          onClick={() => setCompartir(d)}
                          className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-[#25D366] hover:bg-accent"
                          title="Enviar el PDF al WhatsApp del cliente"
                        >
                          <MessageCircle className="h-3.5 w-3.5" />
                          WhatsApp
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {items.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-4 py-14 text-center text-sm text-muted-foreground">
                      <Receipt className="mx-auto h-8 w-8 text-muted-foreground/50" />
                      <p className="mt-2">
                        {debounced
                          ? `Sin resultados para "${debounced}".`
                          : "Aún no se ha emitido ningún comprobante. Emite desde una venta confirmada."}
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

      <CompartirComprobanteModal
        open={Boolean(compartir)}
        onClose={() => setCompartir(null)}
        comprobanteId={compartir?.id ?? null}
        titulo={compartir ? `${TIPO_COMP_LABEL[compartir.tipo]} ${compartir.numero_completo}` : ""}
      />
    </div>
  )
}
