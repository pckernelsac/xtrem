import { useEffect, useMemo, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { Loader2 } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { Button, Field, FormError, Input, Select } from "@/components/ui/Form"
import { Modal } from "@/components/ui/Modal"
import { soles, type FichaDetail } from "@/features/fichas/types"
import { METODOS, type MetodoPago } from "@/features/ventas/types"

/** Qué papel se le entrega al cliente al cobrar el servicio. */
type Documento = "NOTA_VENTA" | "ELECTRONICO"

type Props = {
  open: boolean
  onClose: () => void
  ficha: FichaDetail
  /** Requiere `ventas.crear`: la nota de venta no pasa por SUNAT. */
  puedeNotaVenta: boolean
  /** Requiere `facturacion.emitir`. */
  puedeElectronico: boolean
}

/** El tipo de comprobante lo decide el documento del cliente, igual que en ventas. */
function tipoComprobante(tipoDocumento: string): "FACTURA" | "BOLETA" {
  return tipoDocumento === "RUC" ? "FACTURA" : "BOLETA"
}

export function CobrarFacturarModal({
  open,
  onClose,
  ficha,
  puedeNotaVenta,
  puedeElectronico,
}: Props) {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const saldo = Number(ficha.saldo)
  const [documento, setDocumento] = useState<Documento>(
    puedeElectronico ? "ELECTRONICO" : "NOTA_VENTA",
  )
  const [metodo, setMetodo] = useState<MetodoPago>("EFECTIVO")
  const [recibido, setRecibido] = useState("")
  const [referencia, setReferencia] = useState("")

  // Reabrir el modal tras un error no debe conservar la elección anterior si
  // los permisos ya no la admiten.
  useEffect(() => {
    if (open) setDocumento(puedeElectronico ? "ELECTRONICO" : "NOTA_VENTA")
  }, [open, puedeElectronico])

  const esEfectivo = metodo === "EFECTIVO"
  const montoRecibido = Number(recibido) || 0
  const vuelto = useMemo(() => montoRecibido - saldo, [montoRecibido, saldo])
  // En efectivo hay que entregar al menos el saldo; en digital se cobra exacto.
  const faltaEfectivo = esEfectivo && montoRecibido < saldo

  const tipo = tipoComprobante(ficha.cliente.tipo_documento)
  const tipoLabel = tipo === "FACTURA" ? "factura" : "boleta"
  const esElectronico = documento === "ELECTRONICO"
  const docLabel = esElectronico ? tipoLabel : "nota de venta"

  const cobrar = useMutation({
    mutationFn: async () => {
      // Si el adelanto ya cubrió todo, no hay saldo que cobrar: se emite sin pago.
      const pagos =
        saldo > 0
          ? [
              {
                metodo,
                monto: saldo,
                referencia: !esEfectivo && referencia.trim() ? referencia.trim() : null,
              },
            ]
          : []
      const ruta = esElectronico ? "facturar" : "cobrar"
      const { data } = await api.post(`${API_PREFIX}/fichas/${ficha.id}/${ruta}`, { pagos })
      return data as { id: string }
    },
    onSuccess: (creado) => {
      qc.invalidateQueries({ queryKey: ["fichas"] })
      qc.invalidateQueries({ queryKey: ["ventas"] })
      qc.invalidateQueries({ queryKey: ["caja"] })
      qc.invalidateQueries({ queryKey: ["documentos"] })
      onClose()
      navigate(esElectronico ? `/documentos/${creado.id}` : `/ventas/${creado.id}`)
    },
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Cobrar servicio"
      description={`Servicio N° ${ficha.numero} · se emitirá una ${docLabel}`}
    >
      <div className="space-y-1.5 rounded-md border border-border bg-muted/40 px-3 py-2.5 text-sm">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Total del servicio</span>
          <span className="tabular">{soles(ficha.total)}</span>
        </div>
        {Number(ficha.adelanto) > 0 && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Adelanto</span>
            <span className="tabular">− {soles(ficha.adelanto)}</span>
          </div>
        )}
        <div className="flex justify-between border-t border-border pt-1.5 font-semibold">
          <span>Saldo a cobrar</span>
          <span className="tabular text-base">{soles(saldo)}</span>
        </div>
      </div>

      <Field
        label="Documento a entregar"
        className="mt-4"
        hint={
          esElectronico
            ? "Se declara ante SUNAT y el cliente recibe el PDF oficial."
            : "Documento interno del mostrador. No tiene validez tributaria; podrás emitir la boleta o factura después sin volver a cobrar."
        }
      >
        <Select
          value={documento}
          onChange={(e) => setDocumento(e.target.value as Documento)}
        >
          {puedeElectronico && (
            <option value="ELECTRONICO">
              {tipo === "FACTURA" ? "Factura electrónica" : "Boleta electrónica"}
            </option>
          )}
          {puedeNotaVenta && <option value="NOTA_VENTA">Nota de venta</option>}
        </Select>
      </Field>

      <Field label="Método de pago del saldo" className="mt-4">
        <Select value={metodo} onChange={(e) => setMetodo(e.target.value as MetodoPago)}>
          {METODOS.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </Select>
      </Field>

      {esEfectivo ? (
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field label="Monto recibido">
            <Input
              type="number"
              min="0"
              step="0.01"
              value={recibido}
              onChange={(e) => setRecibido(e.target.value)}
              placeholder={saldo.toFixed(2)}
              autoFocus
            />
          </Field>
          <Field label="Vuelto">
            <div
              className={
                "tabular flex h-9 items-center rounded-md border border-border px-3 text-base font-semibold " +
                (faltaEfectivo ? "text-state-danger" : "text-foreground")
              }
            >
              {faltaEfectivo ? "Falta " + soles(saldo - montoRecibido) : soles(Math.max(0, vuelto))}
            </div>
          </Field>
        </div>
      ) : (
        <Field label="Referencia / N° de operación (opcional)" className="mt-4">
          <Input
            value={referencia}
            onChange={(e) => setReferencia(e.target.value)}
            placeholder="Código de la operación Yape/Plin, voucher..."
          />
        </Field>
      )}

      <div className="mt-4">
        <FormError
          message={
            cobrar.isError
              ? apiErrorMessage(cobrar.error, `No se pudo emitir la ${docLabel}`)
              : null
          }
        />
      </div>

      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancelar
        </Button>
        <Button disabled={cobrar.isPending || faltaEfectivo} onClick={() => cobrar.mutate()}>
          {cobrar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          Cobrar y emitir {docLabel}
        </Button>
      </div>
    </Modal>
  )
}
