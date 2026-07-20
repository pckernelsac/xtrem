import { useEffect, useState } from "react"
import { Loader2, Plus, Trash2 } from "lucide-react"

import { apiErrorMessage } from "@/lib/api"
import { cn } from "@/lib/utils"
import { Button, FormError, Input, Select } from "@/components/ui/Form"
import { Modal } from "@/components/ui/Modal"
import { METODOS, soles, type MetodoPago } from "./types"

export type LineaPago = { metodo: MetodoPago; monto: string; referencia: string }

export function PagoModal({
  open,
  onClose,
  total,
  onConfirmar,
  cargando,
  error,
  cajaAbierta,
  titulo = "Cobrar",
}: {
  open: boolean
  onClose: () => void
  total: number
  onConfirmar: (pagos: LineaPago[]) => void
  cargando: boolean
  error: unknown
  cajaAbierta: boolean
  titulo?: string
}) {
  const [pagos, setPagos] = useState<LineaPago[]>([])

  useEffect(() => {
    if (open) {
      setPagos([{ metodo: "EFECTIVO", monto: total.toFixed(2), referencia: "" }])
    }
  }, [open, total])

  const set = (i: number, campo: keyof LineaPago, valor: string) =>
    setPagos((p) => p.map((x, j) => (j === i ? { ...x, [campo]: valor } : x)))

  const cubierto = pagos.reduce((acc, p) => acc + (Number(p.monto) || 0), 0)
  const falta = Math.round((total - cubierto) * 100) / 100
  const usaEfectivo = pagos.some((p) => p.metodo === "EFECTIVO" && Number(p.monto) > 0)
  const bloqueadoPorCaja = usaEfectivo && !cajaAbierta

  return (
    <Modal open={open} onClose={onClose} title={titulo} description={`Total a cobrar: ${soles(total)}`}>
      <div className="space-y-3">
        {pagos.map((p, i) => {
          const digital = p.metodo !== "EFECTIVO"
          return (
            <div key={i} className="rounded-md border border-border p-3">
              <div className="flex gap-2">
                <Select
                  value={p.metodo}
                  onChange={(e) => set(i, "metodo", e.target.value)}
                  className="w-40"
                >
                  {METODOS.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.label}
                    </option>
                  ))}
                </Select>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={p.monto}
                  onChange={(e) => set(i, "monto", e.target.value)}
                  placeholder="0.00"
                />
                <button
                  type="button"
                  onClick={() => setPagos((x) => x.filter((_, j) => j !== i))}
                  disabled={pagos.length === 1}
                  className="rounded p-2 text-muted-foreground hover:bg-accent hover:text-state-danger disabled:opacity-30"
                  aria-label="Quitar pago"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>

              {digital && (
                <Input
                  value={p.referencia}
                  onChange={(e) => set(i, "referencia", e.target.value)}
                  placeholder="N° de operación o voucher"
                  className="mt-2 text-xs"
                />
              )}
            </div>
          )
        })}

        <Button
          type="button"
          variant="secondary"
          onClick={() =>
            setPagos((p) => [
              ...p,
              {
                metodo: "YAPE",
                monto: falta > 0 ? falta.toFixed(2) : "",
                referencia: "",
              },
            ])
          }
        >
          <Plus className="h-3.5 w-3.5" />
          Dividir el pago
        </Button>

        <div
          className={cn(
            "rounded-md border px-3 py-2.5 text-sm",
            Math.abs(falta) < 0.01
              ? "border-state-success/30 bg-state-success/10 text-state-success"
              : "border-state-warning/30 bg-state-warning/10 text-state-warning",
          )}
        >
          {Math.abs(falta) < 0.01 ? (
            <>El pago cubre el total exacto.</>
          ) : falta > 0 ? (
            <>
              Faltan <span className="tabular font-semibold">{soles(falta)}</span> por cubrir.
            </>
          ) : (
            <>
              El pago excede el total en{" "}
              <span className="tabular font-semibold">{soles(-falta)}</span>. Registra sólo lo
              cobrado; el vuelto no se anota.
            </>
          )}
        </div>

        {bloqueadoPorCaja && (
          <div className="rounded-md border border-state-danger/30 bg-state-danger/10 px-3 py-2.5 text-sm text-state-danger">
            No hay caja abierta. Ábrela antes de cobrar en efectivo, o usa un método digital.
          </div>
        )}

        <FormError message={error ? apiErrorMessage(error, "No se pudo cobrar") : null} />

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            disabled={cargando || Math.abs(falta) >= 0.01 || bloqueadoPorCaja}
            onClick={() => onConfirmar(pagos)}
          >
            {cargando && <Loader2 className="h-4 w-4 animate-spin" />}
            Confirmar {soles(total)}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
