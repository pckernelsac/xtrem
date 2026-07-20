import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "react-router-dom"
import {
  ArrowLeft,
  Ban,
  FileCode2,
  FileText,
  Loader2,
  Receipt,
  RefreshCw,
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
  ESTADO_COMP_INFO,
  TIPO_COMP_LABEL,
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

  const anulable = d.estado === "ACEPTADO" || d.estado === "REGISTRADO"

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
            <Button
              variant="secondary"
              onClick={() => consultar.mutate()}
              disabled={consultar.isPending}
            >
              {consultar.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" />
              )}
              Consultar SUNAT
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

      <div className="rounded-lg border border-border bg-card p-5">
        <div className="flex flex-wrap items-center gap-3">
          <Badge tone={ESTADO_COMP_INFO[d.estado].tone}>
            {d.descripcion_estado_sunat ?? ESTADO_COMP_INFO[d.estado].label}
          </Badge>
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

        <div className="mt-4 flex flex-wrap gap-3 border-t border-border pt-4">
          {[
            { url: d.xml_url, label: "XML firmado", icon: FileCode2 },
            { url: d.pdf_url, label: "PDF", icon: FileText },
            { url: d.cdr_url, label: "CDR", icon: Receipt },
          ].map((a) => (
            <a
              key={a.label}
              href={a.url ?? undefined}
              target="_blank"
              rel="noreferrer"
              className={
                a.url
                  ? "inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-accent"
                  : "inline-flex cursor-not-allowed items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground/40"
              }
              onClick={(e) => !a.url && e.preventDefault()}
            >
              <a.icon className="h-3.5 w-3.5" />
              {a.label}
            </a>
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
