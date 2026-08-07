import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "react-router-dom"
import {
  ArrowLeft,
  Ban,
  CloudOff,
  FileCode2,
  FileText,
  Loader2,
  MessageCircle,
  Receipt,
  RefreshCw,
  Send,
} from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { usePermission } from "@/lib/auth"
import { Badge } from "@/components/ui/Badge"
import { Button, Field, FormError, Input } from "@/components/ui/Form"
import { Modal } from "@/components/ui/Modal"
import { PageHeader } from "@/components/ui/PageHeader"
import { SkeletonCard } from "@/components/ui/skeleton"
import { fmtFechaHora } from "@/features/clientes/types"
import {
  ARCHIVO_INFO,
  abrirArchivo,
  type ArchivoComprobante,
} from "@/features/facturacion/archivos"
import { CompartirComprobanteModal } from "@/features/facturacion/CompartirComprobanteModal"
import {
  TIPO_COMP_LABEL,
  estadoComprobante,
  type ComprobanteDetail,
} from "@/features/facturacion/types"

function Dato({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm">{value || "—"}</dd>
    </div>
  )
}

export default function DocumentoDetailPage() {
  const { id = "" } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const canAnular = usePermission("facturacion.anular")
  const [anularOpen, setAnularOpen] = useState(false)
  const [compartirOpen, setCompartirOpen] = useState(false)
  const [bajando, setBajando] = useState<ArchivoComprobante | null>(null)
  const [motivo, setMotivo] = useState("")

  const { data: d, isLoading } = useQuery({
    queryKey: ["facturacion", "documentos", id],
    queryFn: async () =>
      (await api.get<ComprobanteDetail>(`${API_PREFIX}/facturacion/documentos/${id}`)).data,
    enabled: Boolean(id),
  })

  const invalidar = () => qc.invalidateQueries({ queryKey: ["facturacion"] })

  const consultar = useMutation({
    mutationFn: async () => {
      await api.post(`${API_PREFIX}/facturacion/documentos/${id}/consultar`)
    },
    onSuccess: invalidar,
  })

  const anular = useMutation({
    mutationFn: async () => {
      await api.post(`${API_PREFIX}/facturacion/documentos/${id}/anular`, {
        motivo: motivo.trim(),
      })
    },
    onSuccess: () => {
      invalidar()
      setAnularOpen(false)
    },
  })

  if (isLoading) {
    return (
      <div className="space-y-4">
        <SkeletonCard />
        <SkeletonCard className="h-48" />
      </div>
    )
  }

  if (!d) {
    return (
      <div className="grid h-full place-items-center text-sm text-muted-foreground">
        Comprobante no encontrado.
      </div>
    )
  }

  // Un comprobante en cola no se puede anular todavía: la baja llegaría a SUNAT
  // antes que el propio documento.
  const anulable = (d.estado === "ACEPTADO" || d.estado === "REGISTRADO") && !d.envio_pendiente

  return (
    <div>
      <button
        onClick={() => navigate("/documentos")}
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Volver a documentos
      </button>

      <PageHeader
        title={`${TIPO_COMP_LABEL[d.tipo]} ${d.numero_completo}`}
        description={`${d.cliente_denominacion} · ${d.cliente_numero_documento}`}
        actions={
          <div className="flex flex-wrap gap-2">
            {d.estado !== "ERROR" && (
              <Button variant="secondary" onClick={() => setCompartirOpen(true)}>
                <MessageCircle className="h-3.5 w-3.5 text-[#25D366]" />
                Enviar por WhatsApp
              </Button>
            )}
            {/* El mismo botón: para un comprobante en cola, «consultar» sólo
                puede querer decir «intenta entregarlo ahora», y eso hace. */}
            <Button
              variant={d.envio_pendiente ? "primary" : "secondary"}
              onClick={() => consultar.mutate()}
              disabled={consultar.isPending}
              title={
                d.envio_pendiente
                  ? "Vuelve a mandar este mismo comprobante a SUNAT"
                  : "Refresca el estado guardado"
              }
            >
              {consultar.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : d.envio_pendiente ? (
                <Send className="h-3.5 w-3.5" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" />
              )}
              {d.envio_pendiente ? "Reenviar a SUNAT" : "Consultar SUNAT"}
            </Button>
            {canAnular && anulable && (
              <Button variant="danger" onClick={() => setAnularOpen(true)}>
                <Ban className="h-3.5 w-3.5" />
                Anular
              </Button>
            )}
          </div>
        }
      />

      {d.es_simulado && (
        <div className="mb-4 rounded-md border border-state-warning/40 bg-state-warning/10 px-4 py-3 text-sm text-state-warning">
          Comprobante <strong>simulado</strong>: generado sin envío a SUNAT. No tiene validez
          tributaria.
        </div>
      )}

      {/* Lo importante de este aviso es la última frase: quien atiende tiene que
          saber que NO debe volver a emitir, o la serie acaba con dos documentos
          para el mismo número en cuanto SUNAT vuelva. */}
      {d.envio_pendiente && (
        <div className="mb-4 flex items-start gap-2 rounded-md border border-state-warning/40 bg-state-warning/10 px-4 py-3 text-sm text-state-warning">
          <CloudOff className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-medium">Registrado: pendiente de envío a SUNAT</p>
            <p className="text-xs">
              El comprobante está emitido y firmado con su número definitivo, y el cliente ya
              puede llevarse el PDF. SUNAT no respondió al enviarlo, así que se reenviará solo
              cada pocos minutos hasta que lo acepte
              {d.intentos_envio > 1 && ` (${d.intentos_envio} intentos)`}.{" "}
              <strong>No lo vuelvas a emitir</strong>: se duplicaría el correlativo.
            </p>
            {/* Lo que contestó SUNAT, en crudo: es lo único que distingue una
                caída de un problema de red nuestro. */}
            {d.mensaje_error && <p className="mt-1 text-xs opacity-70">{d.mensaje_error}</p>}
          </div>
        </div>
      )}

      <div className="rounded-lg border border-border bg-card p-5">
        <div className="flex flex-wrap items-center gap-3">
          <Badge tone={estadoComprobante(d).tone}>{estadoComprobante(d).label}</Badge>
          <span className="tabular text-sm text-muted-foreground">
            Emitido {fmtFechaHora(d.created_at)}
          </span>
          {d.venta && (
            <Link
              to={`/ventas/${d.venta.id}`}
              className="text-sm text-primary hover:underline"
            >
              · Venta {d.venta.numero}
            </Link>
          )}
        </div>

        {d.estado === "ERROR" && d.mensaje_error && (
          <div className="mt-4 rounded-md border border-state-danger/30 bg-state-danger/10 px-3 py-2.5 text-sm text-state-danger">
            {d.mensaje_error}
          </div>
        )}
        {d.estado === "ANULADO" && d.motivo_anulacion && (
          <div className="mt-4 rounded-md border border-state-danger/30 bg-state-danger/10 px-3 py-2.5 text-sm text-state-danger">
            Anulado: {d.motivo_anulacion}
          </div>
        )}

        <dl className="mt-5 grid gap-4 border-t border-border pt-4 sm:grid-cols-2 lg:grid-cols-4">
          <Dato label="Tipo" value={TIPO_COMP_LABEL[d.tipo]} />
          <Dato label="Serie-número" value={d.numero_completo} />
          <Dato label="Moneda" value={d.moneda} />
          <Dato label="Fecha de emisión" value={d.fecha_emision} />
          <Dato label="Receptor" value={d.cliente_denominacion} />
          <Dato
            label="Documento receptor"
            value={`${d.cliente_tipo_documento} · ${d.cliente_numero_documento}`}
          />
          <Dato label="Total" value={d.venta ? `S/ ${Number(d.venta.total).toFixed(2)}` : "—"} />
          <Dato label="Emitido por" value={d.usuario?.full_name} />
        </dl>

        {d.hash_cpe && (
          <div className="mt-4 border-t border-border pt-4">
            <dt className="text-xs text-muted-foreground">Hash CPE</dt>
            <dd className="tabular mt-0.5 break-all text-xs">{d.hash_cpe}</dd>
          </div>
        )}

        {/* Los tres archivos se piden al servidor con la sesión abierta: el PDF
            se genera al momento y el XML firmado y el CDR salen de la base. */}
        <div className="mt-4 flex flex-wrap gap-3 border-t border-border pt-4">
          {(
            [
              { archivo: "pdf", label: "PDF", icon: FileText, hay: true },
              { archivo: "xml", label: "XML firmado", icon: FileCode2, hay: d.tiene_xml },
              { archivo: "cdr", label: "CDR", icon: Receipt, hay: d.tiene_cdr },
            ] as const
          ).map((a) => (
            <button
              key={a.label}
              onClick={() => {
                setBajando(a.archivo)
                abrirArchivo(d, a.archivo).finally(() => setBajando(null))
              }}
              disabled={!a.hay || bajando !== null}
              title={a.hay ? ARCHIVO_INFO[a.archivo].titulo : "Todavía no disponible"}
              className={
                a.hay
                  ? "inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-accent disabled:opacity-50"
                  : "inline-flex cursor-not-allowed items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground/40"
              }
            >
              {bajando === a.archivo ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <a.icon className="h-3.5 w-3.5" />
              )}
              {a.label}
            </button>
          ))}
        </div>
      </div>

      {/* JSON enviado — el patrón de FactPro expone el payload para depurar. */}
      {d.payload_enviado && (
        <details className="mt-4 rounded-lg border border-border bg-card p-5">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            JSON enviado a FactPro
          </summary>
          <pre className="mt-3 max-h-80 overflow-auto rounded-md bg-muted/50 p-3 text-xs">
            {JSON.stringify(d.payload_enviado, null, 2)}
          </pre>
        </details>
      )}

      <CompartirComprobanteModal
        open={compartirOpen}
        onClose={() => setCompartirOpen(false)}
        comprobanteId={d.id}
        titulo={`${TIPO_COMP_LABEL[d.tipo]} ${d.numero_completo}`}
      />

      <Modal
        open={anularOpen}
        onClose={() => setAnularOpen(false)}
        title="Anular comprobante"
        description={`${TIPO_COMP_LABEL[d.tipo]} ${d.numero_completo}`}
      >
        <p className="text-sm text-muted-foreground">
          Se comunicará la baja a SUNAT. Esto <strong>no revierte la venta</strong> (stock ni
          caja); si además quieres deshacer la venta, anúlala por separado desde su detalle.
        </p>
        <Field label="Motivo" required className="mt-4">
          <Input
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Error en los datos del comprobante"
          />
        </Field>
        <div className="mt-4">
          <FormError message={anular.isError ? apiErrorMessage(anular.error) : null} />
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setAnularOpen(false)}>
            Cancelar
          </Button>
          <Button
            variant="danger"
            disabled={anular.isPending || motivo.trim().length < 3}
            onClick={() => anular.mutate()}
          >
            {anular.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Anular comprobante
          </Button>
        </div>
      </Modal>
    </div>
  )
}
