import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, Send } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { usePermission } from "@/lib/auth"
import { Badge } from "@/components/ui/Badge"
import { Button, FormError } from "@/components/ui/Form"
import { SkeletonCard } from "@/components/ui/skeleton"
import { fmtFecha, fmtFechaHora } from "@/features/clientes/types"
import { soles } from "@/features/ventas/types"
import {
  ESTADO_LOTE_INFO,
  TIPO_LOTE_LABEL,
  type DiaPendiente,
  type Lote,
} from "@/features/facturacion/types"

/**
 * Declaración de boletas a SUNAT.
 *
 * Emitir una boleta **no la declara**: SUNAT sólo la da por informada cuando
 * llega en un resumen diario, y hay plazo. Esta vista existe para que ese paso
 * no se olvide, porque un olvido no se nota hasta que ya es una infracción.
 */
export function DeclaracionSunat() {
  const qc = useQueryClient()
  const canEmitir = usePermission("facturacion.emitir")

  const pendientes = useQuery({
    queryKey: ["facturacion", "lotes", "pendientes"],
    queryFn: async () =>
      (await api.get<DiaPendiente[]>(`${API_PREFIX}/facturacion/lotes/pendientes`)).data,
  })

  const lotes = useQuery({
    queryKey: ["facturacion", "lotes"],
    queryFn: async () =>
      (await api.get<Lote[]>(`${API_PREFIX}/facturacion/lotes`, { params: { limite: 20 } })).data,
  })

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ["facturacion"] })
    qc.invalidateQueries({ queryKey: ["sistema"] })
  }

  const declarar = useMutation({
    mutationFn: async (fecha: string) => {
      await api.post(`${API_PREFIX}/facturacion/lotes/resumen`, { fecha })
    },
    onSuccess: invalidar,
  })

  const recoger = useMutation({
    mutationFn: async () => {
      await api.post(`${API_PREFIX}/facturacion/lotes/recoger`)
    },
    onSuccess: invalidar,
  })

  const dias = pendientes.data ?? []
  const historial = lotes.data ?? []
  const hayPendientesDeCdr = historial.some((l) => l.pendiente_de_cdr)

  if (pendientes.isLoading) return <SkeletonCard className="h-40" />

  return (
    <div className="space-y-4">
      {/* ---------- Días sin declarar ---------- */}
      <div className="rounded-lg border border-border bg-card p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Boletas por declarar
            </h2>
            <p className="mt-1 max-w-xl text-sm text-muted-foreground">
              Emitir una boleta no la declara ante SUNAT: hay que informarla en el resumen
              diario. La jornada de hoy se declara mañana, cuando ya no puedan entrar más.
            </p>
          </div>
          {hayPendientesDeCdr && (
            <Button
              variant="secondary"
              onClick={() => recoger.mutate()}
              disabled={recoger.isPending}
              title="Consulta a SUNAT el resultado de los resúmenes ya enviados"
            >
              {recoger.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              Actualizar estados
            </Button>
          )}
        </div>

        {dias.length === 0 ? (
          <div className="mt-4 flex items-center gap-2 rounded-md border border-state-success/30 bg-state-success/10 px-3 py-2.5 text-sm text-state-success">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            Todas las boletas emitidas están declaradas.
          </div>
        ) : (
          <table className="mt-4 w-full text-sm">
            <thead>
              <tr className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <th className="pb-2">Día</th>
                <th className="pb-2 text-right">Boletas</th>
                <th className="pb-2 pr-6 text-right">Total</th>
                <th className="pb-2 pl-2">Antigüedad</th>
                <th className="pb-2" />
              </tr>
            </thead>
            <tbody>
              {dias.map((d) => (
                <tr key={d.fecha} className="border-t border-border">
                  <td className="tabular py-2.5 font-medium">{fmtFecha(d.fecha)}</td>
                  <td className="tabular py-2.5 text-right">{d.boletas}</td>
                  <td className="tabular py-2.5 pr-6 text-right">{soles(d.total ?? 0)}</td>
                  <td className="py-2.5 pl-2">
                    {d.fuera_de_plazo ? (
                      <span className="inline-flex items-center gap-1.5 text-state-danger">
                        <AlertTriangle className="h-3.5 w-3.5" />
                        {d.dias_transcurridos} días · fuera de plazo
                      </span>
                    ) : (
                      <span className="text-muted-foreground">
                        {d.dias_transcurridos === 0
                          ? "Hoy"
                          : `${d.dias_transcurridos} día${d.dias_transcurridos > 1 ? "s" : ""}`}
                      </span>
                    )}
                  </td>
                  <td className="py-2.5 text-right">
                    {canEmitir && (
                      <Button
                        onClick={() => declarar.mutate(d.fecha)}
                        disabled={declarar.isPending}
                        title={`Declara a SUNAT las boletas del ${fmtFecha(d.fecha)}`}
                      >
                        {declarar.isPending ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Send className="h-3.5 w-3.5" />
                        )}
                        Declarar
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div className="mt-3">
          <FormError
            message={
              declarar.isError
                ? apiErrorMessage(declarar.error, "No se pudo enviar el resumen")
                : recoger.isError
                  ? apiErrorMessage(recoger.error, "No se pudo consultar a SUNAT")
                  : null
            }
          />
        </div>
      </div>

      {/* ---------- Historial de envíos ---------- */}
      <div className="rounded-lg border border-border">
        <h2 className="border-b border-border px-5 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Enviado a SUNAT
        </h2>
        {lotes.isLoading ? (
          <div className="p-5">
            <SkeletonCard className="h-24" />
          </div>
        ) : historial.length === 0 ? (
          <p className="px-5 py-10 text-center text-sm text-muted-foreground">
            Todavía no se ha enviado ningún resumen ni comunicación de baja.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-secondary">
                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-2.5">Documento</th>
                  <th className="px-4 py-2.5">Tipo</th>
                  <th className="px-4 py-2.5">Día declarado</th>
                  <th className="px-4 py-2.5 text-right">Comprobantes</th>
                  <th className="px-4 py-2.5">Estado</th>
                  <th className="px-4 py-2.5">Respuesta de SUNAT</th>
                </tr>
              </thead>
              <tbody>
                {historial.map((l, i) => (
                  <tr
                    key={l.id}
                    className={
                      i % 2 === 1 ? "border-t border-border bg-muted/30" : "border-t border-border"
                    }
                  >
                    <td className="tabular px-4 py-2.5 font-medium">
                      {l.identificador}
                      <div className="text-xs font-normal text-muted-foreground">
                        {fmtFechaHora(l.created_at)}
                      </div>
                    </td>
                    <td className="px-4 py-2.5">{TIPO_LOTE_LABEL[l.tipo]}</td>
                    <td className="tabular px-4 py-2.5">{fmtFecha(l.fecha_referencia)}</td>
                    <td className="tabular px-4 py-2.5 text-right">{l.cantidad}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1.5">
                        <Badge tone={ESTADO_LOTE_INFO[l.estado].tone}>
                          {ESTADO_LOTE_INFO[l.estado].label}
                        </Badge>
                        {l.es_simulado && <Badge tone="warning">Prueba</Badge>}
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground">
                      {l.descripcion_sunat || l.mensaje_error || "—"}
                      {/* El ticket importa: sin él no se puede recoger el CDR. */}
                      {l.pendiente_de_cdr && l.ticket && (
                        <div className="tabular mt-0.5">Ticket {l.ticket}</div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
