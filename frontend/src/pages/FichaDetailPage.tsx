import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "react-router-dom"
import {
  ArrowLeft,
  Ban,
  Download,
  ExternalLink,
  FileText,
  Loader2,
  MessageCircle,
  Pencil,
  Printer,
  Receipt,
  ShoppingCart,
} from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { usePermission } from "@/lib/auth"
import { Badge } from "@/components/ui/Badge"
import { Button, Field, FormError, Input, Select } from "@/components/ui/Form"
import { Modal } from "@/components/ui/Modal"
import { PageHeader } from "@/components/ui/PageHeader"
import { SkeletonCard } from "@/components/ui/skeleton"
import { fmtFechaHora } from "@/features/clientes/types"
import { CobrarFacturarModal } from "@/features/fichas/CobrarFacturarModal"
import { CompartirModal } from "@/features/fichas/CompartirModal"
import { CompartirVentaModal } from "@/features/ventas/CompartirVentaModal"
import { METODOS, type MetodoPago } from "@/features/ventas/types"
import {
  ESTADOS,
  ESTADOS_FINALES,
  ESTADO_INFO,
  soles,
  tiempoTexto,
  type EstadoFicha,
  type FichaDetail,
} from "@/features/fichas/types"

function Dato({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm">{value || "—"}</dd>
    </div>
  )
}

export default function FichaDetailPage() {
  const { id = "" } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const canEdit = usePermission("fichas.editar")
  const canEstado = usePermission("fichas.cambiar_estado")
  const canImprimir = usePermission("fichas.imprimir")
  const canCancelar = usePermission("fichas.eliminar")
  const canFacturar = usePermission("facturacion.emitir")
  const canVender = usePermission("ventas.crear")

  const [estadoOpen, setEstadoOpen] = useState(false)
  const [cancelarOpen, setCancelarOpen] = useState(false)
  const [compartirOpen, setCompartirOpen] = useState(false)
  const [cobrarOpen, setCobrarOpen] = useState(false)
  const [compartirVentaOpen, setCompartirVentaOpen] = useState(false)
  const [adelantoOpen, setAdelantoOpen] = useState(false)

  const [nuevoEstado, setNuevoEstado] = useState<EstadoFicha>("EN_REVISION")
  const [comentario, setComentario] = useState("")
  const [imprimiendo, setImprimiendo] = useState(false)
  const [nuevoAdelanto, setNuevoAdelanto] = useState("")
  const [adelantoMetodo, setAdelantoMetodo] = useState<MetodoPago>("EFECTIVO")
  const [motivoAdelanto, setMotivoAdelanto] = useState("")

  const { data: f, isLoading } = useQuery({
    queryKey: ["fichas", id],
    queryFn: async () => (await api.get<FichaDetail>(`${API_PREFIX}/fichas/${id}`)).data,
    enabled: Boolean(id),
  })

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ["fichas"] })
    qc.invalidateQueries({ queryKey: ["bicicletas"] })
  }

  const cambiarEstado = useMutation({
    mutationFn: async () => {
      await api.post(`${API_PREFIX}/fichas/${id}/estado`, {
        estado: nuevoEstado,
        comentario: comentario.trim() || null,
      })
    },
    onSuccess: () => {
      invalidar()
      setEstadoOpen(false)
      setComentario("")
    },
  })

  // Corregir el adelanto mueve caja: el backend compensa la diferencia en la
  // sesión abierta, así que sólo se manda el importe final que debía quedar.
  const ajustarAdelanto = useMutation({
    mutationFn: async () => {
      const monto = Number(nuevoAdelanto) || 0
      await api.patch(`${API_PREFIX}/fichas/${id}/adelanto`, {
        adelanto: monto,
        adelanto_metodo: monto > 0 ? adelantoMetodo : null,
        motivo: motivoAdelanto.trim() || null,
      })
    },
    onSuccess: () => {
      invalidar()
      qc.invalidateQueries({ queryKey: ["caja"] })
      setAdelantoOpen(false)
      setMotivoAdelanto("")
    },
  })

  const abrirAjusteAdelanto = () => {
    if (!f) return
    setNuevoAdelanto(Number(f.adelanto) ? String(Number(f.adelanto)) : "")
    setAdelantoMetodo(f.adelanto_metodo ?? "EFECTIVO")
    setMotivoAdelanto("")
    ajustarAdelanto.reset()
    setAdelantoOpen(true)
  }

  const cancelar = useMutation({
    mutationFn: async () => {
      await api.delete(`${API_PREFIX}/fichas/${id}`)
    },
    onSuccess: () => {
      invalidar()
      setCancelarOpen(false)
    },
  })

  // Subir una nota de venta ya cobrada a comprobante electrónico. El saldo ya
  // entró a caja al emitirla, así que va sin pagos: el backend reutiliza la
  // misma venta y no vuelve a cobrar.
  const emitirSobreNota = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ id: string }>(
        `${API_PREFIX}/fichas/${id}/facturar`,
        { pagos: [] },
      )
      return data
    },
    onSuccess: (comprobante) => {
      invalidar()
      qc.invalidateQueries({ queryKey: ["documentos"] })
      navigate(`/documentos/${comprobante.id}`)
    },
  })

  // Los PDF se piden con el cliente autenticado (el navegador no manda la
  // cabecera Authorization en una navegación normal) y se abren como blob.
  const abrirPdf = async (
    recurso: "pdf" | "ticket",
    modo: "ver" | "descargar" | "imprimir",
  ) => {
    setImprimiendo(true)
    try {
      const res = await api.get(`${API_PREFIX}/fichas/${id}/${recurso}`, {
        responseType: "blob",
      })
      const url = URL.createObjectURL(res.data as Blob)

      if (modo === "descargar") {
        const a = document.createElement("a")
        a.href = url
        a.download = `${recurso === "ticket" ? "ticket" : "ficha"}-${f?.numero}.pdf`
        a.click()
      } else if (modo === "imprimir") {
        // El ticket va directo al diálogo de impresión: en el mostrador se
        // imprime muchas veces seguidas y abrir el visor cada vez estorba.
        const marco = document.createElement("iframe")
        marco.style.display = "none"
        marco.src = url
        document.body.appendChild(marco)
        marco.onload = () => marco.contentWindow?.print()
        setTimeout(() => marco.remove(), 60_000)
      } else {
        window.open(url, "_blank")
      }

      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } finally {
      setImprimiendo(false)
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <SkeletonCard />
        <SkeletonCard className="h-64" />
      </div>
    )
  }

  if (!f) {
    return (
      <div className="grid h-full place-items-center text-sm text-muted-foreground">
        Servicio no encontrado.
      </div>
    )
  }

  const cerrada = ESTADOS_FINALES.includes(f.estado)
  const biciTexto = f.bicicleta
    ? [f.bicicleta.marca, f.bicicleta.modelo].filter(Boolean).join(" ")
    : "Sin bicicleta"
  // El servicio se cobra una sola vez: mientras no exista la venta se puede
  // elegir el papel (nota de venta o comprobante electrónico); después ya sólo
  // queda subir esa nota de venta a boleta o factura.
  const cobrable = f.estado === "ENTREGADA" && Number(f.total) > 0
  const puedeCobrar = cobrable && !f.facturacion && (canFacturar || canVender)
  const notaSinComprobante = Boolean(f.facturacion && !f.facturacion.comprobante_id)
  const puedeEmitirSobreNota = canFacturar && notaSinComprobante
  // El adelanto se corrige hasta que exista la venta: después ya es un pago de
  // esa venta y del comprobante, y sólo se arregla anulando o con nota de
  // crédito. Se permite con la ficha entregada, que es cuando salta el error.
  const puedeAjustarAdelanto = canEdit && !f.facturacion && f.estado !== "CANCELADA"

  return (
    <div>
      <button
        onClick={() => navigate("/fichas")}
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Volver a servicios
      </button>

      <PageHeader
        title={`Servicio N° ${f.numero}`}
        description={`${f.cliente.nombre} · ${biciTexto}`}
        actions={
          <div className="flex flex-wrap gap-2">
            {puedeCobrar && (
              <Button onClick={() => setCobrarOpen(true)}>
                <Receipt className="h-3.5 w-3.5" />
                Cobrar servicio
              </Button>
            )}
            {puedeEmitirSobreNota && (
              <Button
                onClick={() => emitirSobreNota.mutate()}
                disabled={emitirSobreNota.isPending}
              >
                {emitirSobreNota.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Receipt className="h-3.5 w-3.5" />
                )}
                Emitir {f.cliente.tipo_documento === "RUC" ? "factura" : "boleta"}
              </Button>
            )}
            {canImprimir && (
              <>
                <Button
                  variant="secondary"
                  onClick={() => abrirPdf("pdf", "ver")}
                  disabled={imprimiendo}
                >
                  {imprimiendo ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <FileText className="h-3.5 w-3.5" />
                  )}
                  Ficha A4
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => abrirPdf("ticket", "imprimir")}
                  disabled={imprimiendo}
                  title="Imprime el ticket de 80 mm en la impresora térmica"
                >
                  <Printer className="h-3.5 w-3.5" />
                  Ticket 80 mm
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => abrirPdf("pdf", "descargar")}
                  disabled={imprimiendo}
                >
                  <Download className="h-3.5 w-3.5" />
                  Descargar
                </Button>
                <Button
                  onClick={() => setCompartirOpen(true)}
                  className="bg-[#25D366] hover:bg-[#25D366]/90"
                >
                  <MessageCircle className="h-3.5 w-3.5" />
                  WhatsApp
                </Button>
              </>
            )}
            {canEdit && !cerrada && (
              <Link to={`/fichas/${f.id}/editar`}>
                <Button variant="secondary">
                  <Pencil className="h-3.5 w-3.5" />
                  Editar
                </Button>
              </Link>
            )}
            {canEstado && !cerrada && <Button onClick={() => setEstadoOpen(true)}>Cambiar estado</Button>}
          </div>
        }
      />

      {/* ---------- Resumen ---------- */}
      <div className="rounded-lg border border-border bg-card p-5">
        <div className="flex flex-wrap items-center gap-3">
          <Badge tone={ESTADO_INFO[f.estado].tone}>{ESTADO_INFO[f.estado].label}</Badge>
          <span className="tabular text-sm text-muted-foreground">
            Recepción: {fmtFechaHora(f.fecha_recepcion)}
          </span>
          {f.fecha_entrega && (
            <span className="tabular text-sm text-muted-foreground">
              · Entrega: {fmtFechaHora(f.fecha_entrega)}
            </span>
          )}
        </div>

        <dl className="mt-5 grid gap-4 border-t border-border pt-4 sm:grid-cols-2 lg:grid-cols-4">
          <Dato
            label="Cliente"
            value={
              <Link to={`/clientes/${f.cliente.id}`} className="hover:text-primary hover:underline">
                {f.cliente.nombre}
              </Link>
            }
          />
          <Dato label="Documento" value={`${f.cliente.tipo_documento} ${f.cliente.numero_documento}`} />
          <Dato label="Teléfono" value={f.cliente.telefono} />
          <Dato
            label="Bicicleta"
            value={
              f.bicicleta ? (
                <Link
                  to={`/bicicletas/${f.bicicleta.id}`}
                  className="hover:text-primary hover:underline"
                >
                  {[f.bicicleta.marca, f.bicicleta.modelo, f.bicicleta.color]
                    .filter(Boolean)
                    .join(" ")}
                </Link>
              ) : (
                <span className="text-muted-foreground">Sin bicicleta</span>
              )
            }
          />
          <Dato label="N° de serie" value={f.bicicleta?.numero_serie} />
          <Dato label="Técnico que recibió" value={f.tecnico_recepcion?.full_name} />
          <Dato label="Técnico responsable" value={f.tecnico_responsable?.full_name} />
          <Dato label="¿Cómo nos conoció?" value={f.canal_referencia} />
        </dl>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        {/* ---------- Servicio ---------- */}
        <div className="rounded-lg border border-border bg-card p-5">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Servicio solicitado
          </h2>
          {f.servicios_labels.length > 0 || f.servicio_otro ? (
            <ul className="mt-3 space-y-1.5 text-sm">
              {f.servicios_labels.map((s) => (
                <li key={s} className="flex items-center gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                  {s}
                </li>
              ))}
              {f.servicio_otro && (
                <li className="flex items-center gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                  {f.servicio_otro}
                </li>
              )}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-muted-foreground">Sin servicios marcados.</p>
          )}

          <h3 className="mt-5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Diagnóstico inicial
          </h3>
          <p className="mt-2 whitespace-pre-wrap text-sm">
            {f.diagnostico_inicial || <span className="text-muted-foreground">Sin diagnóstico.</span>}
          </p>
        </div>

        {/* ---------- Repuestos ---------- */}
        <div className="rounded-lg border border-border bg-card p-5">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Repuestos utilizados
          </h2>
          {f.repuestos.length ? (
            <table className="mt-3 w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="pb-1.5 font-medium">Cant.</th>
                  <th className="pb-1.5 font-medium">Descripción</th>
                  <th className="pb-1.5 text-right font-medium">Subtotal</th>
                </tr>
              </thead>
              <tbody>
                {f.repuestos.map((r) => (
                  <tr key={r.id} className="border-t border-border">
                    <td className="tabular py-1.5">{Number(r.cantidad)}</td>
                    <td className="py-1.5">
                      {r.descripcion}
                      {r.marca && (
                        <span className="text-xs text-muted-foreground"> · {r.marca}</span>
                      )}
                      {r.producto ? (
                        <div className="tabular text-xs text-muted-foreground">
                          {r.producto.sku} · descontado del inventario
                        </div>
                      ) : (
                        <div className="text-xs text-muted-foreground">Sin enlazar al almacén</div>
                      )}
                    </td>
                    <td className="tabular py-1.5 text-right">{soles(r.subtotal)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-border">
                  <td colSpan={2} className="pt-2 text-right text-sm font-medium">
                    Subtotal repuestos
                  </td>
                  <td className="tabular pt-2 text-right text-base font-semibold">
                    {soles(f.total_repuestos)}
                  </td>
                </tr>
              </tfoot>
            </table>
          ) : (
            <p className="mt-3 text-sm text-muted-foreground">No se usaron repuestos.</p>
          )}
        </div>
      </div>

      {/* ---------- Cobro ---------- */}
      <div className="mt-4 rounded-lg border border-border bg-card p-5">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Cobro
        </h2>
        <dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-xs text-muted-foreground">Repuestos</dt>
            <dd className="tabular mt-0.5 text-sm">{soles(f.total_repuestos)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Servicio solicitado</dt>
            <dd className="tabular mt-0.5 text-sm">{soles(f.costo_servicio)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Total</dt>
            <dd className="tabular mt-0.5 text-base font-semibold">{soles(f.total)}</dd>
          </div>
          <div>
            <dt className="flex items-center gap-1.5 text-xs text-muted-foreground">
              Adelanto · Saldo
              {puedeAjustarAdelanto && (
                <button
                  onClick={abrirAjusteAdelanto}
                  className="rounded p-0.5 hover:bg-accent hover:text-foreground"
                  title="Corregir el adelanto cobrado en recepción"
                >
                  <Pencil className="h-3 w-3" />
                </button>
              )}
            </dt>
            <dd className="tabular mt-0.5 text-sm">
              {soles(f.adelanto)} · <span className="font-semibold">{soles(f.saldo)}</span>
            </dd>
          </div>
        </dl>

        {f.facturacion ? (
          <div className="mt-4 space-y-3 border-t border-border pt-4">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge tone="success">{f.facturacion.comprobante_id ? "Facturado" : "Cobrado"}</Badge>
              <Link
                to={`/ventas/${f.facturacion.venta_id}`}
                className="inline-flex items-center gap-1.5 hover:text-primary hover:underline"
              >
                <ShoppingCart className="h-3.5 w-3.5" />
                Nota de venta {f.facturacion.venta_numero}
              </Link>
              <button
                onClick={() => setCompartirVentaOpen(true)}
                className="inline-flex items-center gap-1.5 rounded px-1.5 py-0.5 text-muted-foreground hover:bg-accent hover:text-[#25D366]"
                title="Enviar la nota de venta al cliente por WhatsApp"
              >
                <MessageCircle className="h-3.5 w-3.5" />
                WhatsApp
              </button>
            </div>

            {f.facturacion.comprobante_id ? (
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Link
                  to={`/documentos/${f.facturacion.comprobante_id}`}
                  className="inline-flex items-center gap-1.5 hover:text-primary hover:underline"
                >
                  <Receipt className="h-3.5 w-3.5" />
                  {f.facturacion.tipo === "FACTURA" ? "Factura" : "Boleta"} {f.facturacion.numero}
                </Link>
                {f.facturacion.es_simulado && <Badge tone="warning">Prueba</Badge>}
              </div>
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm text-muted-foreground">
                  El saldo ya se cobró con la nota de venta. Si el cliente pide comprobante
                  electrónico, se emite sobre ella sin volver a cobrar.
                </p>
                {puedeEmitirSobreNota && (
                  <Button
                    onClick={() => emitirSobreNota.mutate()}
                    disabled={emitirSobreNota.isPending}
                  >
                    {emitirSobreNota.isPending ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Receipt className="h-3.5 w-3.5" />
                    )}
                    Emitir {f.cliente.tipo_documento === "RUC" ? "factura" : "boleta"}
                  </Button>
                )}
              </div>
            )}

            <FormError
              message={
                emitirSobreNota.isError
                  ? apiErrorMessage(emitirSobreNota.error, "No se pudo emitir el comprobante")
                  : null
              }
            />
          </div>
        ) : (
          cobrable && (
            <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-4">
              <p className="text-sm text-muted-foreground">
                El servicio está entregado y listo para cobrar: nota de venta o comprobante
                electrónico.
              </p>
              {puedeCobrar && (
                <Button onClick={() => setCobrarOpen(true)}>
                  <Receipt className="h-3.5 w-3.5" />
                  Cobrar servicio
                </Button>
              )}
            </div>
          )
        )}
      </div>

      {/* ---------- Trabajo ---------- */}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-border bg-card p-5">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Trabajo realizado
          </h2>
          <p className="mt-2 whitespace-pre-wrap text-sm">
            {f.trabajo_realizado || <span className="text-muted-foreground">Aún sin registrar.</span>}
          </p>
          <p className="mt-3 text-xs text-muted-foreground">
            Tiempo invertido: {tiempoTexto(f.tiempo_invertido_min)}
          </p>
        </div>

        <div className="rounded-lg border border-border bg-card p-5">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Observaciones
          </h2>
          <p className="mt-2 whitespace-pre-wrap text-sm">
            {f.observaciones || <span className="text-muted-foreground">Sin observaciones.</span>}
          </p>
          <p className="mt-3 text-xs text-muted-foreground">
            Garantía: {f.garantia_dias ? `${f.garantia_dias} días` : "no especificada"}
          </p>
        </div>
      </div>

      {/* ---------- Consulta pública ---------- */}
      <div className="mt-4 rounded-lg border border-border bg-card p-5">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Consulta pública del cliente
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          El QR del ticket lleva a esta página de solo lectura, sin necesidad de sesión. También
          puedes compartir el enlace directo.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <code className="tabular rounded-md bg-muted px-2 py-1.5 text-sm">
            /f/{f.codigo_publico}
          </code>
          <a
            href={`${window.location.origin.replace(":5173", ":8000")}/f/${f.codigo_publico}`}
            target="_blank"
            rel="noreferrer"
          >
            <Button variant="secondary">
              <ExternalLink className="h-3.5 w-3.5" />
              Abrir vista pública
            </Button>
          </a>
        </div>
      </div>

      {/* ---------- Historial ---------- */}
      <div className="mt-4 rounded-lg border border-border bg-card p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Historial de estados
          </h2>
          {canCancelar && !cerrada && (
            <Button variant="danger" onClick={() => setCancelarOpen(true)}>
              <Ban className="h-3.5 w-3.5" />
              Cancelar servicio
            </Button>
          )}
        </div>

        <ol className="relative mt-4 space-y-4 border-l border-border pl-5">
          {f.historial_estados.map((h, i) => (
            <li key={i} className="relative">
              <span className="absolute -left-[26px] top-1 h-3 w-3 rounded-full border-2 border-card bg-primary" />
              <p className="text-sm font-medium">
                {h.estado_anterior
                  ? `${ESTADO_INFO[h.estado_anterior].label} → ${ESTADO_INFO[h.estado_nuevo].label}`
                  : ESTADO_INFO[h.estado_nuevo].label}
              </p>
              {h.comentario && <p className="text-sm text-muted-foreground">{h.comentario}</p>}
              <p className="tabular mt-0.5 text-xs text-muted-foreground">
                {fmtFechaHora(h.created_at)}
                {h.usuario && ` · ${h.usuario.full_name}`}
              </p>
            </li>
          ))}
        </ol>
      </div>

      {/* ---------- Modal: cambiar estado ---------- */}
      <Modal
        open={estadoOpen}
        onClose={() => setEstadoOpen(false)}
        title="Cambiar estado"
        description={`Servicio N° ${f.numero} · actualmente ${ESTADO_INFO[f.estado].label}`}
      >
        <Field label="Nuevo estado" required>
          <Select
            value={nuevoEstado}
            onChange={(e) => setNuevoEstado(e.target.value as EstadoFicha)}
          >
            {ESTADOS.filter((e) => e.value !== f.estado && e.value !== "CANCELADA").map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Comentario" className="mt-4">
          <Input
            value={comentario}
            onChange={(e) => setComentario(e.target.value)}
            placeholder="Motivo o detalle del cambio (opcional)"
          />
        </Field>

        <div className="mt-4">
          <FormError
            message={
              cambiarEstado.isError
                ? apiErrorMessage(cambiarEstado.error, "No se pudo cambiar el estado")
                : null
            }
          />
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setEstadoOpen(false)}>
            Cancelar
          </Button>
          <Button disabled={cambiarEstado.isPending} onClick={() => cambiarEstado.mutate()}>
            {cambiarEstado.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Confirmar
          </Button>
        </div>
      </Modal>

      {/* ---------- Modal: corregir el adelanto ---------- */}
      <Modal
        open={adelantoOpen}
        onClose={() => setAdelantoOpen(false)}
        title="Corregir adelanto"
        description={`Servicio N° ${f.numero} · cobrado en recepción ${soles(f.adelanto)}`}
      >
        <div className="flex gap-2">
          <Field label="Adelanto correcto" required className="flex-1">
            <Input
              type="number"
              min="0"
              step="0.01"
              max={Number(f.total)}
              value={nuevoAdelanto}
              onChange={(e) => setNuevoAdelanto(e.target.value)}
              placeholder="0.00"
            />
          </Field>
          <Field label="Método" className="w-40">
            <Select
              value={adelantoMetodo}
              onChange={(e) => setAdelantoMetodo(e.target.value as MetodoPago)}
              disabled={!(Number(nuevoAdelanto) > 0)}
            >
              {METODOS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <Field label="Motivo" className="mt-4" hint="Queda en el historial del servicio.">
          <Input
            value={motivoAdelanto}
            onChange={(e) => setMotivoAdelanto(e.target.value)}
            placeholder="Por qué se corrige (opcional)"
          />
        </Field>

        <p className="mt-4 rounded-md bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
          La diferencia se registra en la caja abierta: un ingreso si el adelanto sube y un
          egreso si baja o se devuelve. Nuevo saldo por cobrar:{" "}
          <span className="tabular font-semibold text-foreground">
            {soles(Number(f.total) - (Number(nuevoAdelanto) || 0))}
          </span>
        </p>

        <div className="mt-4">
          <FormError
            message={
              ajustarAdelanto.isError
                ? apiErrorMessage(ajustarAdelanto.error, "No se pudo corregir el adelanto")
                : null
            }
          />
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setAdelantoOpen(false)}>
            Cancelar
          </Button>
          <Button
            disabled={
              ajustarAdelanto.isPending ||
              nuevoAdelanto.trim() === "" ||
              Number(nuevoAdelanto) < 0 ||
              Number(nuevoAdelanto) > Number(f.total)
            }
            onClick={() => ajustarAdelanto.mutate()}
          >
            {ajustarAdelanto.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Guardar
          </Button>
        </div>
      </Modal>

      <CompartirModal
        open={compartirOpen}
        onClose={() => setCompartirOpen(false)}
        fichaId={f.id}
        numero={f.numero}
        telefonoCliente={f.cliente.telefono}
      />

      <CobrarFacturarModal
        open={cobrarOpen}
        onClose={() => setCobrarOpen(false)}
        ficha={f}
        puedeNotaVenta={canVender}
        puedeElectronico={canFacturar}
      />

      {f.facturacion && (
        <CompartirVentaModal
          open={compartirVentaOpen}
          onClose={() => setCompartirVentaOpen(false)}
          ventaId={f.facturacion.venta_id}
          titulo={`Nota de venta ${f.facturacion.venta_numero}`}
          telefonoCliente={f.cliente.telefono}
        />
      )}


      {/* ---------- Modal: cancelar ---------- */}
      <Modal
        open={cancelarOpen}
        onClose={() => setCancelarOpen(false)}
        title="Cancelar servicio"
        description={`Servicio N° ${f.numero}`}
      >
        <p className="text-sm text-muted-foreground">
          El servicio no se borra: queda en estado <b className="text-foreground">Cancelado</b> con
          registro de quién lo canceló. No se podrá reabrir; si el trabajo continúa, crea un servicio
          nuevo.
        </p>
        {f.repuestos.some((r) => r.producto) && (
          <p className="mt-3 rounded-md border border-border bg-muted/40 px-3 py-2.5 text-sm">
            Los repuestos enlazados al inventario{" "}
            <b className="text-foreground">volverán al stock</b> automáticamente.
          </p>
        )}

        <div className="mt-4">
          <FormError
            message={cancelar.isError ? apiErrorMessage(cancelar.error, "No se pudo cancelar") : null}
          />
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setCancelarOpen(false)}>
            Volver
          </Button>
          <Button variant="danger" disabled={cancelar.isPending} onClick={() => cancelar.mutate()}>
            Cancelar ficha
          </Button>
        </div>
      </Modal>
    </div>
  )
}
