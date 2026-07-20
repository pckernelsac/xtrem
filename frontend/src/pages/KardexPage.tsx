import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { ArrowDownRight, ArrowLeft, ArrowUpRight, SlidersHorizontal } from "lucide-react"

import { api, API_PREFIX } from "@/lib/api"
import { Badge } from "@/components/ui/Badge"
import { Select } from "@/components/ui/Form"
import { PageHeader } from "@/components/ui/PageHeader"
import { Paginacion } from "@/components/ui/Paginacion"
import { SkeletonTable } from "@/components/ui/skeleton"
import { fmtFechaHora, type Page } from "@/features/clientes/types"
import {
  cantidad,
  MOVIMIENTOS,
  soles,
  type Movimiento,
  type Producto,
  type TipoMovimiento,
} from "@/features/inventario/types"

const PAGE_SIZE = 50

const ICONO = {
  ENTRADA: ArrowUpRight,
  SALIDA: ArrowDownRight,
  AJUSTE: SlidersHorizontal,
} as const

export default function KardexPage() {
  const navigate = useNavigate()
  const [productoId, setProductoId] = useState("")
  const [tipo, setTipo] = useState<TipoMovimiento | "">("")
  const [page, setPage] = useState(1)

  const productosQ = useQuery({
    queryKey: ["inventario", "productos", "select"],
    queryFn: async () =>
      (
        await api.get<Page<Producto>>(`${API_PREFIX}/inventario/productos`, {
          params: { page_size: 200 },
        })
      ).data,
  })

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["inventario", "kardex", { productoId, tipo, page }],
    queryFn: async () =>
      (
        await api.get<Page<Movimiento>>(`${API_PREFIX}/inventario/kardex`, {
          params: {
            producto_id: productoId || undefined,
            tipo: tipo || undefined,
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
      <button
        onClick={() => navigate("/inventario")}
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Volver a inventario
      </button>

      <PageHeader
        title="Kardex"
        description="Libro de movimientos del almacén. Cada línea guarda el stock antes y después."
      />

      <div className="mb-4 flex flex-wrap gap-2">
        <Select
          value={productoId}
          onChange={(e) => {
            setProductoId(e.target.value)
            setPage(1)
          }}
          className="w-72 py-1.5"
        >
          <option value="">Todos los productos</option>
          {(productosQ.data?.items ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.sku} · {p.nombre}
            </option>
          ))}
        </Select>

        <Select
          value={tipo}
          onChange={(e) => {
            setTipo(e.target.value as TipoMovimiento | "")
            setPage(1)
          }}
          className="w-44 py-1.5"
        >
          <option value="">Todos los tipos</option>
          {MOVIMIENTOS.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </Select>
      </div>

      {isLoading ? (
        <SkeletonTable
          rows={10}
          headers={["Fecha", "Producto", "Tipo", "Cantidad", "Antes", "Después", "Motivo", "Usuario"]}
          columns={["w-32", "w-40", "w-20", "w-16", "w-16", "w-16", "w-32", "w-28"]}
        />
      ) : (
        <div className={isFetching ? "opacity-60 transition-opacity" : "transition-opacity"}>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-secondary">
                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-2.5">Fecha</th>
                  <th className="px-4 py-2.5">Producto</th>
                  <th className="px-4 py-2.5">Tipo</th>
                  <th className="px-4 py-2.5 text-right">Cantidad</th>
                  <th className="px-4 py-2.5 text-right">Antes</th>
                  <th className="px-4 py-2.5 text-right">Después</th>
                  <th className="px-4 py-2.5">Motivo</th>
                  <th className="px-4 py-2.5">Usuario</th>
                </tr>
              </thead>
              <tbody>
                {items.map((m, i) => {
                  const info = MOVIMIENTOS.find((x) => x.value === m.tipo)!
                  const Icono = ICONO[m.tipo]
                  return (
                    <tr
                      key={m.id}
                      className={
                        i % 2 === 1
                          ? "border-t border-border bg-muted/30"
                          : "border-t border-border"
                      }
                    >
                      <td className="tabular px-4 py-2.5 text-muted-foreground">
                        {fmtFechaHora(m.created_at)}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className="tabular font-medium">{m.producto.sku}</span>
                        <div className="text-xs text-muted-foreground">{m.producto.nombre}</div>
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge tone={info.tone}>
                          <Icono className="mr-1 h-3 w-3" />
                          {info.label}
                        </Badge>
                      </td>
                      <td className="tabular px-4 py-2.5 text-right font-medium">
                        {m.tipo === "ENTRADA" ? "+" : m.tipo === "SALIDA" ? "−" : "±"}
                        {cantidad(m.cantidad)}
                      </td>
                      <td className="tabular px-4 py-2.5 text-right text-muted-foreground">
                        {cantidad(m.stock_anterior)}
                      </td>
                      <td className="tabular px-4 py-2.5 text-right font-medium">
                        {cantidad(m.stock_posterior)}
                      </td>
                      <td className="px-4 py-2.5 text-muted-foreground">
                        {m.motivo || "—"}
                        {m.costo_unitario && (
                          <div className="tabular text-xs">
                            costo {soles(m.costo_unitario)}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-muted-foreground">
                        {m.usuario?.full_name ?? "—"}
                      </td>
                    </tr>
                  )
                })}
                {items.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-4 py-12 text-center text-sm text-muted-foreground">
                      No hay movimientos con estos filtros.
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
            etiqueta="movimientos"
          />
        </div>
      )}
    </div>
  )
}
