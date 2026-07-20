import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "react-router-dom"
import {
  ArrowLeft,
  Ban,
  CheckCircle2,
  FileDown,
  Loader2,
  Printer,
  Receipt,
  XCircle,
} from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { usePermission } from "@/lib/auth"
import { Badge } from "@/components/ui/Badge"
import { Button, Field, FormError, Input } from "@/components/ui/Form"
import { Modal } from "@/components/ui/Modal"
import { PageHeader } from "@/components/ui/PageHeader"
import { SkeletonCard } from "@/components/ui/skeleton"
import { fmtFecha, fmtFechaHora } from "@/features/clientes/types"
import { PagoModal, type LineaPago } from "@/features/ventas/PagoModal"
import {
  ESTADO_VENTA_INFO,
  METODO_LABEL,
  soles,
  type Arqueo,
  type VentaDetail,
} from "@/features/ventas/types"

export default function VentaDetailPage() {
  const { id = "" } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const canAnular = usePermission("ventas.anular")
  const canConvertir = usePermission("ventas.crear")
  const canEditar = usePermission("ventas.editar")
  const canFacturar = usePermission("facturacion.emitir")

  const [anularOpen, setAnularOpen] = useState(false)
  const [motivo, setMotivo] = useState("")
  const [convertirOpen, setConvertirOpen] = useState(false)

  const { data: v, isLoading } = useQuery({
    queryKey: ["ventas", id],
    queryFn: async () => (await api.get<VentaDetail>(`${API_PREFIX}/ventas/${id}`)).data,
    enabled: Boolean(id),
  })

  const caja = useQuery({
    queryKey: ["caja", "actual"],
    queryFn: async () => (await api.get<Arqueo | null>(`${API_PREFIX}/caja/actual`)).data,
    enabled: Boolean(v && v.tipo === "COTIZACION" && v.estado === "PENDIENTE"),
  })

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ["ventas"] })
    qc.invalidateQueries({ queryKey: ["caja"] })
    qc.invalidateQueries({ queryKey: ["inventario"] })
  }

  const anular = useMutation({
    mutationFn: async () => {
      await api.post(`${API_PREFIX}/ventas/${id}/anular`, { motivo: motivo.trim() || null })
    },
    onSuccess: () => {
      invalidar()
      setAnularOpen(false)
    },
  })

  const rechazar = useMutation({
    mutationFn: async () => {
      await api.post(`${API_PREFIX}/ventas/${id}/rechazar`)
    },
    onSuccess: invalidar,
  })

  const convertir = useMutation({
    mutationFn: async (pagos: LineaPago[]) => {
      await api.post(`${API_PREFIX}/ventas/${id}/convertir`, {
        pagos: pagos.map((p) => ({
          metodo: p.metodo,
          monto: Number(p.monto),
          referencia: p.referencia.trim() || null,
        })),
      })
    },
    onSuccess: () => {
      invalidar()
      setConvertirOpen(false)
    },
  })

  const emitir = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ id: string }>(`${API_PREFIX}/facturacion/emitir`, {
        venta_id: id,
      })
      return data
    },
    onSuccess: (comp) => {
      invalidar()
      navigate(`/documentos/${comp.id}`)
    },
  })

  if (isLoading) {
    return (
      <div className="space-y-4">
        <SkeletonCard />
        <SkeletonCard className="h-64" />
      </div>
    )
  }

  if (!v) {
    return (
      <div className="grid h-full place-items-center text-sm text-muted-foreground">
        Documento no encontrado.
      </div>
    )
  }

  const esCotizacion = v.tipo === "COTIZACION"
  const pendiente = v.estado === "PENDIENTE"

  // El PDF se pide con el cliente autenticado —una navegación normal no manda
  // la cabecera Authorization— y se descarga como blob.
  const descargar = async (formato: "pdf" | "ticket") => {
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

  return (
    <div>
      <button
        onClick={() => navigate(esCotizacion ? "/cotizaciones" : "/ventas")}
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Volver
      </button>

      <PageHeader
        title={`${esCotizacion ? "Cotización" : "Venta"} ${v.numero}`}
        description={
          v.cliente
            ? `${v.cliente.nombre} · ${v.cliente.tipo_documento} ${v.cliente.numero_documento}`
            : "Público general"
        }
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => descargar("pdf")}>
              <FileDown className="h-4 w-4" />
              PDF A4
            </Button>
            <Button variant="secondary" onClick={() => descargar("ticket")}>
              <Printer className="h-4 w-4" />
              Ticket 80 mm
            </Button>
            {esCotizacion && pendiente && canConvertir && (
              <Button onClick={() => setConvertirOpen(true)}>
                <CheckCircle2 className="h-4 w-4" />
                Convertir en venta
              </Button>
            )}
            {esCotizacion && pendiente && canEditar && (
              <>
                <Link to={`/ventas/${v.id}/editar`}>
                  <Button variant="secondary">Editar</Button>
                </Link>
                <Button
                  variant="danger"
                  disabled={rechazar.isPending}
                  onClick={() => rechazar.mutate()}
                >
                  <XCircle className="h-4 w-4" />
                  Rechazar
                </Button>
              </>
            )}
            {!esCotizacion && v.estado === "CONFIRMADA" && canFacturar && (
              <Button onClick={() => emitir.mutate()} disabled={emitir.isPending}>
                {emitir.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Receipt className="h-4 w-4" />
                )}
                Emitir comprobante
              </Button>
            )}
            {!esCotizacion && v.estado === "CONFIRMADA" && canAnular && (
              <Button variant="danger" onClick={() => setAnularOpen(true)}>
                <Ban className="h-4 w-4" />
                Anular
              </Button>
            )}
          </div>
        }
      />

      <div className="rounded-lg border border-border bg-card p-5">
        <div className="flex flex-wrap items-center gap-3">
          <Badge tone={ESTADO_VENTA_INFO[v.estado].tone}>{ESTADO_VENTA_INFO[v.estado].label}</Badge>
          {v.vencida && <Badge tone="danger">Vencida</Badge>}
          <span className="tabular text-sm text-muted-foreground">{fmtFechaHora(v.created_at)}</span>
          {v.usuario && (
            <span className="text-sm text-muted-foreground">· {v.usuario.full_name}</span>
          )}
          {esCotizacion && v.valido_hasta && (
            <span className="text-sm text-muted-foreground">
              · Válida hasta {fmtFecha(v.valido_hasta)}
            </span>
          )}
        </div>

        {emitir.isError && (
          <div className="mt-4 rounded-md border border-state-danger/30 bg-state-danger/10 px-3 py-2.5 text-sm text-state-danger">
            {apiErrorMessage(emitir.error, "No se pudo emitir el comprobante")}
          </div>
        )}

        {v.estado === "ANULADA" && v.motivo_anulacion && (
          <div className="mt-4 rounded-md border border-state-danger/30 bg-state-danger/10 px-3 py-2.5 text-sm text-state-danger">
            Anulada{v.fecha_anulacion ? ` el ${fmtFechaHora(v.fecha_anulacion)}` : ""}:{" "}
            {v.motivo_anulacion}
          </div>
        )}

        <div className="mt-5 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <th className="pb-2">Descripción</th>
                <th className="pb-2 text-right">Cant.</th>
                <th className="pb-2 text-right">P. unit.</th>
                <th className="pb-2 text-right">Dscto.</th>
                <th className="pb-2 text-right">Importe</th>
              </tr>
            </thead>
            <tbody>
              {v.items.map((it) => (
                <tr key={it.id} className="border-t border-border">
                  <td className="py-2">
                    {it.descripcion}
                    {it.producto && (
                      <span className="tabular block text-xs text-muted-foreground">
                        {it.producto.sku}
                      </span>
                    )}
                  </td>
                  <td className="tabular py-2 text-right">{Number(it.cantidad)}</td>
                  <td className="tabular py-2 text-right">{soles(it.precio_unitario)}</td>
                  <td className="tabular py-2 text-right text-muted-foreground">
                    {Number(it.descuento) > 0 ? `−${soles(it.descuento)}` : "—"}
                  </td>
                  <td className="tabular py-2 text-right font-medium">{soles(it.subtotal)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-4 flex justify-end">
          <div className="w-64 space-y-1.5 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Subtotal</span>
              <span className="tabular">{soles(v.subtotal)}</span>
            </div>
            {Number(v.descuento) > 0 && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Descuento</span>
                <span className="tabular text-state-danger">−{soles(v.descuento)}</span>
              </div>
            )}
            <div className="flex justify-between border-t border-border pt-1.5 text-base font-semibold">
              <span>Total</span>
              <span className="tabular">{soles(v.total)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* -------------------- Pagos -------------------- */}
      {!esCotizacion && (
        <div className="mt-4 rounded-lg border border-border bg-card p-5">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Pagos
          </h2>
          {v.pagos.length ? (
            <table className="mt-3 w-full text-sm">
              <tbody>
                {v.pagos.map((p) => (
                  <tr key={p.id} className="border-t border-border first:border-0">
                    <td className="py-2">{METODO_LABEL[p.metodo]}</td>
                    <td className="py-2 text-muted-foreground">{p.referencia || ""}</td>
                    <td className="tabular py-2 text-right font-medium">{soles(p.monto)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">Sin pagos registrados.</p>
          )}
        </div>
      )}

      {v.notas && (
        <div className="mt-4 rounded-lg border border-border bg-card p-5">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Notas
          </h2>
          <p className="mt-2 whitespace-pre-wrap text-sm">{v.notas}</p>
        </div>
      )}

      {/* -------------------- Modales -------------------- */}
      <Modal
        open={anularOpen}
        onClose={() => setAnularOpen(false)}
        title="Anular venta"
        description={v.numero}
      >
        <p className="text-sm text-muted-foreground">
          Se devolverá la mercadería al inventario y el dinero cobrado saldrá de la caja abierta.
          La venta queda registrada como anulada; no se borra.
        </p>
        <Field label="Motivo" className="mt-4">
          <Input
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Motivo de la anulación"
          />
        </Field>
        <div className="mt-4">
          <FormError message={anular.isError ? apiErrorMessage(anular.error) : null} />
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setAnularOpen(false)}>
            Cancelar
          </Button>
          <Button variant="danger" disabled={anular.isPending} onClick={() => anular.mutate()}>
            {anular.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Anular venta
          </Button>
        </div>
      </Modal>

      <PagoModal
        open={convertirOpen}
        onClose={() => setConvertirOpen(false)}
        total={Number(v.total)}
        titulo={`Cobrar cotización ${v.numero}`}
        cargando={convertir.isPending}
        error={convertir.isError ? convertir.error : null}
        cajaAbierta={Boolean(caja.data)}
        onConfirmar={(pagos) => convertir.mutate(pagos)}
      />
    </div>
  )
}
