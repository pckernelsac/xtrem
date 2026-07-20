import { useEffect, useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { FileSpreadsheet, Loader2 } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { Button, Field, FormError, Input, Select } from "@/components/ui/Form"
import { Modal } from "@/components/ui/Modal"

/** Primer y último día del mes de una fecha, en formato ISO. */
function mesDe(hoy: Date) {
  const primero = new Date(hoy.getFullYear(), hoy.getMonth(), 1)
  const ultimo = new Date(hoy.getFullYear(), hoy.getMonth() + 1, 0)
  const iso = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
  return { desde: iso(primero), hasta: iso(ultimo) }
}

export function ExportarContadorModal({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const [desde, setDesde] = useState("")
  const [hasta, setHasta] = useState("")
  const [tipo, setTipo] = useState("")

  // El contador declara por mes, así que el periodo abierto es el del mes en
  // curso; cambiarlo es un caso, no el caso normal.
  useEffect(() => {
    if (!open) return
    const m = mesDe(new Date())
    setDesde(m.desde)
    setHasta(m.hasta)
    setTipo("")
  }, [open])

  const descargar = useMutation({
    mutationFn: async () => {
      const res = await api.get(`${API_PREFIX}/facturacion/documentos/export`, {
        params: { desde, hasta, tipo: tipo || undefined },
        responseType: "blob",
      })
      const url = URL.createObjectURL(res.data as Blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `registro-ventas-${desde}-${hasta}.xlsx`
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    },
    onSuccess: onClose,
  })

  const rangoInvalido = Boolean(desde && hasta && hasta < desde)

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Excel para el contador"
      description="Registro de ventas del periodo, con base imponible, IGV y estado ante SUNAT"
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Desde" required>
          <Input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} />
        </Field>
        <Field label="Hasta" required hint="Incluido en el periodo">
          <Input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} />
        </Field>
      </div>

      <Field label="Tipo de comprobante" className="mt-4">
        <Select value={tipo} onChange={(e) => setTipo(e.target.value)}>
          <option value="">Todos</option>
          <option value="BOLETA">Sólo boletas</option>
          <option value="FACTURA">Sólo facturas</option>
          <option value="NOTA_CREDITO">Sólo notas de crédito</option>
        </Select>
      </Field>

      <p className="mt-4 text-xs text-muted-foreground">
        Se filtra por <strong>fecha de emisión</strong>, que es la que declara el periodo. El
        archivo trae una hoja con el detalle documento por documento y otra con el resumen
        cuadrado por tipo. Los anulados y rechazados aparecen tachados y no suman.
      </p>

      {rangoInvalido && (
        <p className="mt-3 text-xs text-state-danger">
          La fecha final no puede ser anterior a la inicial.
        </p>
      )}

      <FormError
        message={descargar.isError ? apiErrorMessage(descargar.error, "No se pudo exportar") : null}
      />

      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancelar
        </Button>
        <Button
          disabled={!desde || !hasta || rangoInvalido || descargar.isPending}
          onClick={() => descargar.mutate()}
        >
          {descargar.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FileSpreadsheet className="h-4 w-4" />
          )}
          Descargar Excel
        </Button>
      </div>
    </Modal>
  )
}
