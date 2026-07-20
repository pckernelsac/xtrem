import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { Button, Field, FormError, Input, Select, Textarea } from "@/components/ui/Form"
import { Modal } from "@/components/ui/Modal"
import { TIPOS_BICICLETA, type Bicicleta, type Cliente, type Page, type TipoBicicleta } from "./types"

type FormState = {
  cliente_id: string
  marca: string
  modelo: string
  color: string
  numero_serie: string
  tipo: TipoBicicleta
  rodado: string
  talla: string
  anio: string
  notas: string
}

const VACIO: FormState = {
  cliente_id: "",
  marca: "",
  modelo: "",
  color: "",
  numero_serie: "",
  tipo: "MTB",
  rodado: "",
  talla: "",
  anio: "",
  notas: "",
}

export function BicicletaFormModal({
  open,
  onClose,
  bicicleta,
  clienteId,
}: {
  open: boolean
  onClose: () => void
  bicicleta?: Bicicleta | null
  /** Preselecciona el dueño al crear desde la ficha de un cliente. */
  clienteId?: string
}) {
  const qc = useQueryClient()
  const [form, setForm] = useState<FormState>(VACIO)

  // Sólo se listan clientes activos: no tiene sentido dar de alta una bici
  // a nombre de alguien dado de baja.
  const clientesQ = useQuery({
    queryKey: ["clientes", "activos-select"],
    queryFn: async () =>
      (
        await api.get<Page<Cliente>>(`${API_PREFIX}/clientes`, {
          params: { is_active: true, page_size: 200 },
        })
      ).data,
    enabled: open,
  })

  useEffect(() => {
    if (!open) return
    setForm(
      bicicleta
        ? {
            cliente_id: bicicleta.cliente_id,
            marca: bicicleta.marca,
            modelo: bicicleta.modelo ?? "",
            color: bicicleta.color ?? "",
            numero_serie: bicicleta.numero_serie ?? "",
            tipo: bicicleta.tipo,
            rodado: bicicleta.rodado ?? "",
            talla: bicicleta.talla ?? "",
            anio: bicicleta.anio?.toString() ?? "",
            notas: bicicleta.notas ?? "",
          }
        : { ...VACIO, cliente_id: clienteId ?? "" },
    )
  }, [open, bicicleta, clienteId])

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }))

  const guardar = useMutation({
    mutationFn: async () => {
      const payload = {
        cliente_id: form.cliente_id,
        marca: form.marca,
        modelo: form.modelo.trim() || null,
        color: form.color.trim() || null,
        numero_serie: form.numero_serie.trim() || null,
        tipo: form.tipo,
        rodado: form.rodado.trim() || null,
        talla: form.talla.trim() || null,
        anio: form.anio ? Number(form.anio) : null,
        notas: form.notas.trim() || null,
      }
      if (bicicleta) await api.patch(`${API_PREFIX}/bicicletas/${bicicleta.id}`, payload)
      else await api.post(`${API_PREFIX}/bicicletas`, payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bicicletas"] })
      qc.invalidateQueries({ queryKey: ["clientes"] })
      onClose()
    },
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={bicicleta ? "Editar bicicleta" : "Nueva bicicleta"}
      description={bicicleta?.descripcion ?? "Registra la bicicleta y su dueño"}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          guardar.mutate()
        }}
        className="space-y-4"
      >
        <Field label="Cliente (dueño)" required>
          <Select
            required
            value={form.cliente_id}
            onChange={(e) => set("cliente_id", e.target.value)}
            disabled={clientesQ.isLoading}
          >
            <option value="">
              {clientesQ.isLoading ? "Cargando clientes..." : "Selecciona un cliente"}
            </option>
            {(clientesQ.data?.items ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.nombre} · {c.tipo_documento} {c.numero_documento}
              </option>
            ))}
          </Select>
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Marca" required>
            <Input
              required
              value={form.marca}
              onChange={(e) => set("marca", e.target.value)}
              placeholder="Trek"
            />
          </Field>
          <Field label="Modelo">
            <Input
              value={form.modelo}
              onChange={(e) => set("modelo", e.target.value)}
              placeholder="Marlin 7"
            />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Tipo" required>
            <Select value={form.tipo} onChange={(e) => set("tipo", e.target.value as TipoBicicleta)}>
              {TIPOS_BICICLETA.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Color">
            <Input
              value={form.color}
              onChange={(e) => set("color", e.target.value)}
              placeholder="Rojo"
            />
          </Field>
        </div>

        <Field
          label="N° de serie"
          hint="Se guarda en mayúsculas y sin espacios. Déjalo vacío si no es legible."
        >
          <Input
            value={form.numero_serie}
            onChange={(e) => set("numero_serie", e.target.value)}
            placeholder="WTU123XY"
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Rodado">
            <Input
              value={form.rodado}
              onChange={(e) => set("rodado", e.target.value)}
              placeholder="29"
            />
          </Field>
          <Field label="Talla">
            <Input
              value={form.talla}
              onChange={(e) => set("talla", e.target.value)}
              placeholder="M"
            />
          </Field>
          <Field label="Año">
            <Input
              type="number"
              min={1950}
              max={new Date().getFullYear() + 1}
              value={form.anio}
              onChange={(e) => set("anio", e.target.value)}
              placeholder="2023"
            />
          </Field>
        </div>

        <Field label="Notas">
          <Textarea
            rows={2}
            value={form.notas}
            onChange={(e) => set("notas", e.target.value)}
            placeholder="Accesorios, estado general, detalles..."
          />
        </Field>

        <FormError
          message={guardar.isError ? apiErrorMessage(guardar.error, "No se pudo guardar") : null}
        />

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" disabled={guardar.isPending}>
            {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {bicicleta ? "Guardar cambios" : "Registrar bicicleta"}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
