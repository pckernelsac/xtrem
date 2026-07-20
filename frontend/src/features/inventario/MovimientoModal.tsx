import { useEffect, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { cn } from "@/lib/utils"
import { Button, Field, FormError, Input } from "@/components/ui/Form"
import { Modal } from "@/components/ui/Modal"
import { cantidad, MOVIMIENTOS, type Producto, type TipoMovimiento } from "./types"

export function MovimientoModal({
  open,
  onClose,
  producto,
}: {
  open: boolean
  onClose: () => void
  producto: Producto | null
}) {
  const qc = useQueryClient()
  const [tipo, setTipo] = useState<TipoMovimiento>("ENTRADA")
  const [cant, setCant] = useState("")
  const [costo, setCosto] = useState("")
  const [motivo, setMotivo] = useState("")

  useEffect(() => {
    if (open) {
      setTipo("ENTRADA")
      setCant("")
      setCosto("")
      setMotivo("")
    }
  }, [open])

  const guardar = useMutation({
    mutationFn: async () => {
      await api.post(`${API_PREFIX}/inventario/productos/${producto!.id}/movimientos`, {
        tipo,
        cantidad: Number(cant) || 0,
        costo_unitario: tipo === "ENTRADA" && costo ? Number(costo) : null,
        motivo: motivo.trim() || null,
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["inventario"] })
      onClose()
    },
  })

  if (!producto) return null

  const actual = Number(producto.stock_actual)
  const valor = Number(cant) || 0

  // El ajuste fija el stock contado; entrada y salida lo mueven.
  const resultado =
    tipo === "AJUSTE" ? valor : tipo === "ENTRADA" ? actual + valor : actual - valor

  const info = MOVIMIENTOS.find((m) => m.value === tipo)!
  const insuficiente = tipo === "SALIDA" && valor > actual

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Movimiento de stock"
      description={`${producto.sku} · ${producto.nombre}`}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          guardar.mutate()
        }}
        className="space-y-4"
      >
        <div className="grid grid-cols-3 gap-2">
          {MOVIMIENTOS.map((m) => (
            <button
              key={m.value}
              type="button"
              onClick={() => setTipo(m.value)}
              className={cn(
                "rounded-md border px-3 py-2 text-sm font-medium transition",
                tipo === m.value
                  ? "border-primary bg-primary/5 text-foreground"
                  : "border-border text-muted-foreground hover:bg-accent",
              )}
            >
              {m.label}
            </button>
          ))}
        </div>

        <p className="text-xs text-muted-foreground">{info.ayuda}</p>

        <Field
          label={tipo === "AJUSTE" ? "Stock contado" : "Cantidad"}
          required
          hint={`Stock actual: ${cantidad(producto.stock_actual)} ${producto.unidad.toLowerCase()}`}
        >
          <Input
            required
            autoFocus
            type="number"
            min="0"
            step="0.001"
            value={cant}
            onChange={(e) => setCant(e.target.value)}
          />
        </Field>

        {tipo === "ENTRADA" && (
          <Field
            label="Costo unitario"
            hint="Si lo indicas, actualiza el precio de compra del producto"
          >
            <Input
              type="number"
              min="0"
              step="0.01"
              value={costo}
              onChange={(e) => setCosto(e.target.value)}
              placeholder={String(Number(producto.precio_compra))}
            />
          </Field>
        )}

        <Field label="Motivo">
          <Input
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder={
              tipo === "ENTRADA"
                ? "Compra a proveedor"
                : tipo === "SALIDA"
                  ? "Consumo en taller"
                  : "Conteo físico de almacén"
            }
          />
        </Field>

        {cant !== "" && (
          <div
            className={cn(
              "rounded-md border px-3 py-2.5 text-sm",
              insuficiente
                ? "border-state-danger/30 bg-state-danger/10 text-state-danger"
                : "border-border bg-muted/40",
            )}
          >
            {insuficiente ? (
              <>
                No hay stock suficiente: tienes {cantidad(producto.stock_actual)} y quieres retirar{" "}
                {cantidad(valor)}.
              </>
            ) : (
              <>
                Stock resultante:{" "}
                <span className="tabular font-semibold">{cantidad(resultado)}</span>{" "}
                {producto.unidad.toLowerCase()}
                {tipo === "AJUSTE" && actual !== valor && (
                  <span className="text-muted-foreground">
                    {" "}
                    ({valor > actual ? "+" : ""}
                    {cantidad(valor - actual)} respecto a lo registrado)
                  </span>
                )}
              </>
            )}
          </div>
        )}

        <FormError
          message={
            guardar.isError ? apiErrorMessage(guardar.error, "No se pudo registrar") : null
          }
        />

        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" disabled={guardar.isPending || insuficiente || cant === ""}>
            {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Registrar
          </Button>
        </div>
      </form>
    </Modal>
  )
}
