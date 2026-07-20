import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { ArrowDownRight, ArrowUpRight, ExternalLink } from "lucide-react"

import { api, API_PREFIX } from "@/lib/api"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/Badge"
import { Modal } from "@/components/ui/Modal"
import { Skeleton } from "@/components/ui/skeleton"
import { fmtFechaHora } from "@/features/clientes/types"
import type { Page } from "@/features/clientes/types"
import {
  METODOS,
  METODO_LABEL,
  soles,
  type Arqueo,
  type Venta,
} from "@/features/ventas/types"

const fmtHora = (iso: string) =>
  new Date(iso).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" })

/**
 * Qué se movió en una jornada de caja ya cerrada (o en la de hoy).
 *
 * Las ventas se piden con `incluir_archivadas`: archivar una venta es un gesto
 * de ordenar el listado de trabajo, no de deshacerla, y si se ocultaran aquí
 * el detalle no cuadraría con el total que arqueó el cajero esa noche.
 */
export function JornadaDetalleModal({
  sesionId,
  onClose,
}: {
  sesionId: string | null
  onClose: () => void
}) {
  const arqueo = useQuery({
    queryKey: ["caja", "sesion", sesionId],
    queryFn: async () =>
      (await api.get<Arqueo>(`${API_PREFIX}/caja/sesiones/${sesionId}`)).data,
    enabled: Boolean(sesionId),
  })

  const ventas = useQuery({
    queryKey: ["ventas", "sesion", sesionId],
    queryFn: async () =>
      (
        await api.get<Page<Venta>>(`${API_PREFIX}/ventas`, {
          params: { sesion_caja_id: sesionId, incluir_archivadas: true, page_size: 200 },
        })
      ).data,
    enabled: Boolean(sesionId),
  })

  const s = arqueo.data
  const dif = s?.diferencia == null ? null : Number(s.diferencia)

  return (
    <Modal
      open={Boolean(sesionId)}
      onClose={onClose}
      title={s ? `Jornada ${s.numero}` : "Jornada de caja"}
      description={
        s
          ? `${fmtFechaHora(s.fecha_apertura)} — ${
              s.fecha_cierre ? fmtFechaHora(s.fecha_cierre) : "sigue abierta"
            }`
          : undefined
      }
      className="max-w-4xl"
    >
      {arqueo.isLoading || !s ? (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : (
        <div className="space-y-6">
          {/* ---------- Cuadre ---------- */}
          <div className="grid gap-3 sm:grid-cols-4">
            {[
              ["Monto inicial", soles(s.monto_inicial)],
              ["Efectivo esperado", soles(s.efectivo_esperado)],
              ["Contado al cierre", s.monto_declarado == null ? "—" : soles(s.monto_declarado)],
            ].map(([label, valor]) => (
              <div key={label} className="rounded-lg border border-border px-3 py-2.5">
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className="tabular mt-1 font-semibold">{valor}</p>
              </div>
            ))}
            <div className="rounded-lg border border-border px-3 py-2.5">
              <p className="text-xs text-muted-foreground">Diferencia</p>
              <p
                className={cn(
                  "tabular mt-1 font-semibold",
                  dif === null
                    ? undefined
                    : Math.abs(dif) < 0.01
                      ? "text-state-success"
                      : dif > 0
                        ? "text-state-info"
                        : "text-state-danger",
                )}
              >
                {dif === null ? "—" : `${dif > 0 ? "+" : ""}${soles(dif)}`}
              </p>
            </div>
          </div>

          {/* ---------- Ventas de la jornada ---------- */}
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Ventas de la jornada{" "}
              <span className="tabular font-normal">({ventas.data?.total ?? 0})</span>
            </h3>
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead className="bg-secondary">
                  <tr className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <th className="px-3 py-2">Documento</th>
                    <th className="px-3 py-2">Hora</th>
                    <th className="px-3 py-2">Cliente</th>
                    <th className="px-3 py-2">Estado</th>
                    <th className="px-3 py-2 text-right">Total</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {(ventas.data?.items ?? []).map((v, i) => (
                    <tr
                      key={v.id}
                      className={
                        i % 2 === 1
                          ? "border-t border-border bg-muted/30"
                          : "border-t border-border"
                      }
                    >
                      <td className="tabular px-3 py-2 font-medium">{v.numero}</td>
                      <td className="tabular px-3 py-2 text-muted-foreground">
                        {fmtHora(v.created_at)}
                      </td>
                      <td className="px-3 py-2">
                        {v.cliente?.nombre ?? (
                          <span className="text-muted-foreground">Venta de mostrador</span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <Badge
                          tone={
                            v.estado === "CONFIRMADA"
                              ? "success"
                              : v.estado === "ANULADA"
                                ? "danger"
                                : "neutral"
                          }
                        >
                          {v.estado.charAt(0) + v.estado.slice(1).toLowerCase()}
                        </Badge>
                      </td>
                      <td
                        className={cn(
                          "tabular px-3 py-2 text-right",
                          v.estado === "ANULADA" && "text-muted-foreground line-through",
                        )}
                      >
                        {soles(v.total)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <Link
                          to={`/ventas/${v.id}`}
                          onClick={onClose}
                          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-primary hover:underline"
                          title="Abrir la venta"
                        >
                          Ver <ExternalLink className="h-3 w-3" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                  {(ventas.data?.total ?? 0) === 0 && (
                    <tr>
                      <td
                        colSpan={6}
                        className="px-3 py-8 text-center text-sm text-muted-foreground"
                      >
                        {ventas.isLoading
                          ? "Cargando ventas…"
                          : "No se cobró ninguna venta en esta jornada."}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* ---------- Totales y movimientos ---------- */}
          <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Por método de pago
              </h3>
              <table className="w-full text-sm">
                <tbody>
                  {METODOS.map((m) => {
                    const t = s.totales[m.value]
                    const neto = Number(t?.ingresos ?? 0) - Number(t?.egresos ?? 0)
                    return (
                      <tr key={m.value} className="border-b border-border last:border-0">
                        <td className="py-1.5">{METODO_LABEL[m.value]}</td>
                        <td className="tabular py-1.5 text-right">{soles(neto)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Movimientos de caja{" "}
                <span className="tabular font-normal">({s.movimientos.length})</span>
              </h3>
              <div className="max-h-64 divide-y divide-border overflow-y-auto rounded-lg border border-border">
                {s.movimientos.map((m) => {
                  const ingreso = m.tipo === "INGRESO"
                  return (
                    <div key={m.id} className="flex items-start justify-between gap-3 px-3 py-2">
                      <div className="min-w-0">
                        <p
                          className={cn(
                            "flex items-center gap-1 text-xs font-medium",
                            ingreso ? "text-state-success" : "text-state-danger",
                          )}
                        >
                          {ingreso ? (
                            <ArrowUpRight className="h-3 w-3" />
                          ) : (
                            <ArrowDownRight className="h-3 w-3" />
                          )}
                          {METODO_LABEL[m.metodo]}
                        </p>
                        <p className="truncate text-sm">{m.concepto}</p>
                        <p className="tabular text-xs text-muted-foreground">
                          {fmtFechaHora(m.created_at)} · {m.usuario?.full_name ?? "—"}
                        </p>
                      </div>
                      <span
                        className={cn(
                          "tabular shrink-0 text-sm font-medium",
                          ingreso ? "text-state-success" : "text-state-danger",
                        )}
                      >
                        {ingreso ? "+" : "−"}
                        {soles(m.monto)}
                      </span>
                    </div>
                  )
                })}
                {s.movimientos.length === 0 && (
                  <p className="px-3 py-8 text-center text-sm text-muted-foreground">
                    Sin movimientos registrados.
                  </p>
                )}
              </div>
            </div>
          </div>

          {s.observaciones && (
            <div className="rounded-md bg-muted/50 px-3 py-2.5 text-sm">
              <span className="text-xs font-medium text-muted-foreground">
                Observaciones del cierre
              </span>
              <p className="mt-1 whitespace-pre-wrap">{s.observaciones}</p>
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}
