import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Boxes, Download, FileText, Package, ShoppingCart, Wallet } from "lucide-react"

import { api, API_PREFIX } from "@/lib/api"
import { usePermission } from "@/lib/auth"
import { cn, fechaLocal } from "@/lib/utils"
import { Button, Select } from "@/components/ui/Form"
import { PageHeader } from "@/components/ui/PageHeader"
import { Paginacion, recortarPagina } from "@/components/ui/Paginacion"
import { SkeletonCard, SkeletonStatCard } from "@/components/ui/skeleton"

/** El reporte de inventario llega completo en una respuesta; en un taller con
 *  el stock bajo, «requieren reposición» puede ser casi todo el catálogo. */
const ALERTAS_PAGE_SIZE = 20

const soles = (v: string | number) =>
  `S/ ${Number(v).toLocaleString("es-PE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

type ReporteVentas = {
  cantidad: number
  total: string
  ticket_promedio: string
  por_dia: { fecha: string; cantidad: number; total: string }[]
  por_metodo: Record<string, string>
}
type ReporteProductos = {
  items: { sku: string | null; descripcion: string; cantidad: string; importe: string }[]
}
type ReporteInventario = {
  productos_activos: number
  valor_total: string
  sin_stock: number
  bajo_minimo: number
  alertas: {
    sku: string
    nombre: string
    stock_actual: string
    stock_minimo: string
    estado: string
  }[]
}

const hoy = () => fechaLocal(new Date())
const haceDias = (n: number) => fechaLocal(new Date(Date.now() - n * 86400000))

type Tab = "ventas" | "productos" | "inventario"

export default function ReportesPage() {
  const canExport = usePermission("reportes.exportar")
  const [tab, setTab] = useState<Tab>("ventas")
  const [desde, setDesde] = useState(haceDias(29))
  const [hasta, setHasta] = useState(hoy())
  const [descargando, setDescargando] = useState(false)
  const [alertasPage, setAlertasPage] = useState(1)

  const rango = { desde, hasta }

  const ventas = useQuery({
    queryKey: ["reportes", "ventas", rango],
    queryFn: async () =>
      (await api.get<ReporteVentas>(`${API_PREFIX}/reportes/ventas`, { params: rango })).data,
    enabled: tab === "ventas",
  })
  const productos = useQuery({
    queryKey: ["reportes", "productos", rango],
    queryFn: async () =>
      (
        await api.get<ReporteProductos>(`${API_PREFIX}/reportes/productos-vendidos`, {
          params: rango,
        })
      ).data,
    enabled: tab === "productos",
  })
  const inventario = useQuery({
    queryKey: ["reportes", "inventario"],
    queryFn: async () =>
      (await api.get<ReporteInventario>(`${API_PREFIX}/reportes/inventario`)).data,
    enabled: tab === "inventario",
  })

  const exportar = async (formato: "excel" | "pdf") => {
    setDescargando(true)
    try {
      const rutas: Record<Tab, string> = {
        ventas: "ventas",
        productos: "productos-vendidos",
        inventario: "inventario",
      }
      const params: Record<string, string> =
        tab === "inventario" ? {} : { desde, hasta }
      if (formato === "pdf") params.formato = "pdf"
      const res = await api.get(`${API_PREFIX}/reportes/${rutas[tab]}/export`, {
        params,
        responseType: "blob",
      })
      const url = URL.createObjectURL(res.data as Blob)
      if (formato === "pdf") {
        window.open(url, "_blank")
      } else {
        const a = document.createElement("a")
        a.href = url
        a.download = `${tab}-${desde}.xlsx`
        a.click()
      }
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } finally {
      setDescargando(false)
    }
  }

  const maxDia = Math.max(1, ...(ventas.data?.por_dia ?? []).map((d) => Number(d.total)))

  const TABS: { value: Tab; label: string; icon: typeof ShoppingCart }[] = [
    { value: "ventas", label: "Ventas", icon: ShoppingCart },
    { value: "productos", label: "Más vendidos", icon: Package },
    { value: "inventario", label: "Inventario", icon: Boxes },
  ]

  return (
    <div>
      <PageHeader
        title="Reportes"
        description="Ventas, productos e inventario. Exportables a Excel y PDF."
        actions={
          canExport && (
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => exportar("excel")} disabled={descargando}>
                <Download className="h-4 w-4" />
                Excel
              </Button>
              {tab === "ventas" && (
                <Button variant="secondary" onClick={() => exportar("pdf")} disabled={descargando}>
                  <FileText className="h-4 w-4" />
                  PDF
                </Button>
              )}
            </div>
          )
        }
      />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1 rounded-lg border border-border p-1">
          {TABS.map((t) => (
            <button
              key={t.value}
              onClick={() => setTab(t.value)}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition",
                tab === t.value
                  ? "bg-primary text-white"
                  : "text-muted-foreground hover:bg-accent",
              )}
            >
              <t.icon className="h-3.5 w-3.5" />
              {t.label}
            </button>
          ))}
        </div>

        {tab !== "inventario" && (
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Del</span>
            <input
              type="date"
              value={desde}
              max={hasta}
              onChange={(e) => setDesde(e.target.value)}
              className="rounded-md border border-border bg-background px-2 py-1.5"
            />
            <span className="text-muted-foreground">al</span>
            <input
              type="date"
              value={hasta}
              min={desde}
              max={hoy()}
              onChange={(e) => setHasta(e.target.value)}
              className="rounded-md border border-border bg-background px-2 py-1.5"
            />
            <Select
              className="w-32 py-1.5"
              onChange={(e) => {
                const n = Number(e.target.value)
                if (n) {
                  setDesde(haceDias(n - 1))
                  setHasta(hoy())
                }
              }}
              value=""
            >
              <option value="">Rango…</option>
              <option value="7">7 días</option>
              <option value="30">30 días</option>
              <option value="90">90 días</option>
            </Select>
          </div>
        )}
      </div>

      {/* -------------------- Ventas -------------------- */}
      {tab === "ventas" &&
        (ventas.isLoading || !ventas.data ? (
          <div className="grid gap-4 sm:grid-cols-3">
            <SkeletonStatCard />
            <SkeletonStatCard />
            <SkeletonStatCard />
          </div>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="rounded-lg border border-border bg-card p-5">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Total vendido
                </p>
                <p className="tabular mt-3 text-2xl font-semibold text-primary">
                  {soles(ventas.data.total)}
                </p>
              </div>
              <div className="rounded-lg border border-border bg-card p-5">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  N° de ventas
                </p>
                <p className="tabular mt-3 text-2xl font-semibold">{ventas.data.cantidad}</p>
              </div>
              <div className="rounded-lg border border-border bg-card p-5">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Ticket promedio
                </p>
                <p className="tabular mt-3 text-2xl font-semibold">
                  {soles(ventas.data.ticket_promedio)}
                </p>
              </div>
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_300px]">
              <div className="rounded-lg border border-border bg-card p-5">
                <h2 className="mb-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Ventas por día
                </h2>
                <div className="flex h-56 items-end gap-1">
                  {ventas.data.por_dia.map((d) => (
                    <div
                      key={d.fecha}
                      className="group relative flex h-full flex-1 flex-col justify-end"
                      title={`${d.fecha}: ${soles(d.total)} (${d.cantidad})`}
                    >
                      <div
                        className="w-full rounded-t bg-primary/80 transition group-hover:bg-primary"
                        style={{ height: `${Math.max((Number(d.total) / maxDia) * 100, 1)}%` }}
                      />
                    </div>
                  ))}
                </div>
                <div className="mt-2 flex justify-between text-[10px] text-muted-foreground">
                  <span>{ventas.data.por_dia[0]?.fecha.slice(5)}</span>
                  <span>{ventas.data.por_dia.at(-1)?.fecha.slice(5)}</span>
                </div>
              </div>

              <div className="rounded-lg border border-border bg-card p-5">
                <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Por método de pago
                </h2>
                {Object.entries(ventas.data.por_metodo).length ? (
                  <table className="w-full text-sm">
                    <tbody>
                      {Object.entries(ventas.data.por_metodo).map(([m, monto]) => (
                        <tr key={m} className="border-t border-border first:border-0">
                          <td className="py-2 capitalize">{m.toLowerCase()}</td>
                          <td className="tabular py-2 text-right font-medium">{soles(monto)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="text-sm text-muted-foreground">Sin cobros en el periodo.</p>
                )}
              </div>
            </div>
          </>
        ))}

      {/* -------------------- Productos -------------------- */}
      {tab === "productos" &&
        (productos.isLoading || !productos.data ? (
          <SkeletonCard className="h-96" />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-secondary">
                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-2.5 w-10">#</th>
                  <th className="px-4 py-2.5">SKU</th>
                  <th className="px-4 py-2.5">Producto</th>
                  <th className="px-4 py-2.5 text-right">Vendidos</th>
                  <th className="px-4 py-2.5 text-right">Importe</th>
                </tr>
              </thead>
              <tbody>
                {productos.data.items.map((p, i) => (
                  <tr
                    key={`${p.sku}-${i}`}
                    className={i % 2 === 1 ? "border-t border-border bg-muted/30" : "border-t border-border"}
                  >
                    <td className="tabular px-4 py-2.5 text-muted-foreground">{i + 1}</td>
                    <td className="tabular px-4 py-2.5">{p.sku ?? "—"}</td>
                    <td className="px-4 py-2.5">{p.descripcion}</td>
                    <td className="tabular px-4 py-2.5 text-right">{Number(p.cantidad)}</td>
                    <td className="tabular px-4 py-2.5 text-right font-medium">{soles(p.importe)}</td>
                  </tr>
                ))}
                {productos.data.items.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-12 text-center text-sm text-muted-foreground">
                      Sin ventas en el periodo.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        ))}

      {/* -------------------- Inventario -------------------- */}
      {tab === "inventario" &&
        (inventario.isLoading || !inventario.data ? (
          <div className="grid gap-4 sm:grid-cols-4">
            <SkeletonStatCard />
            <SkeletonStatCard />
            <SkeletonStatCard />
            <SkeletonStatCard />
          </div>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-lg border border-border bg-card p-5">
                <span className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  <Wallet className="h-3.5 w-3.5" /> Valor total
                </span>
                <p className="tabular mt-3 text-2xl font-semibold text-primary">
                  {soles(inventario.data.valor_total)}
                </p>
              </div>
              <div className="rounded-lg border border-border bg-card p-5">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Productos activos
                </p>
                <p className="tabular mt-3 text-2xl font-semibold">
                  {inventario.data.productos_activos}
                </p>
              </div>
              <div className="rounded-lg border border-border bg-card p-5">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Bajo mínimo
                </p>
                <p className="tabular mt-3 text-2xl font-semibold text-state-warning">
                  {inventario.data.bajo_minimo}
                </p>
              </div>
              <div className="rounded-lg border border-border bg-card p-5">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Sin stock
                </p>
                <p className="tabular mt-3 text-2xl font-semibold text-state-danger">
                  {inventario.data.sin_stock}
                </p>
              </div>
            </div>

            <h2 className="mt-6 mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Productos que requieren reposición
            </h2>
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead className="bg-secondary">
                  <tr className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <th className="px-4 py-2.5">SKU</th>
                    <th className="px-4 py-2.5">Producto</th>
                    <th className="px-4 py-2.5 text-right">Stock</th>
                    <th className="px-4 py-2.5 text-right">Mínimo</th>
                    <th className="px-4 py-2.5">Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {recortarPagina(inventario.data.alertas, alertasPage, ALERTAS_PAGE_SIZE).map((a, i) => (
                    <tr
                      key={a.sku}
                      className={i % 2 === 1 ? "border-t border-border bg-muted/30" : "border-t border-border"}
                    >
                      <td className="tabular px-4 py-2.5">{a.sku}</td>
                      <td className="px-4 py-2.5">{a.nombre}</td>
                      <td className="tabular px-4 py-2.5 text-right">{Number(a.stock_actual)}</td>
                      <td className="tabular px-4 py-2.5 text-right text-muted-foreground">
                        {Number(a.stock_minimo)}
                      </td>
                      <td className="px-4 py-2.5">
                        <span
                          className={cn(
                            "rounded-full px-2 py-0.5 text-xs font-medium",
                            a.estado === "SIN_STOCK"
                              ? "bg-state-danger/12 text-state-danger"
                              : "bg-state-warning/12 text-state-warning",
                          )}
                        >
                          {a.estado === "SIN_STOCK" ? "Sin stock" : "Bajo mínimo"}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {inventario.data.alertas.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-12 text-center text-sm text-muted-foreground">
                        Todo el inventario está por encima del mínimo.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <Paginacion
              page={alertasPage}
              pageSize={ALERTAS_PAGE_SIZE}
              total={inventario.data.alertas.length}
              onChange={setAlertasPage}
              etiqueta="productos por reponer"
              singular="producto por reponer"
            />
          </>
        ))}
    </div>
  )
}
