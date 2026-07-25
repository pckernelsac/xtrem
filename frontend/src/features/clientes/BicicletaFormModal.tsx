import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Check, Loader2, X } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { Button, Field, FormError, Input, Select, Textarea } from "@/components/ui/Form"
import { Modal } from "@/components/ui/Modal"
import { BuscarCliente } from "./BuscarCliente"
import {
  TIPOS_BICICLETA,
  type Bicicleta,
  type ClienteBrief,
  type TipoBicicleta,
} from "./types"

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
  onCreated,
}: {
  open: boolean
  onClose: () => void
  bicicleta?: Bicicleta | null
  /** Preselecciona el dueño al crear desde la ficha de un cliente. */
  clienteId?: string
  /** Se llama con la bici recién creada (no al editar): útil para autoseleccionarla. */
  onCreated?: (bicicleta: Bicicleta) => void
}) {
  const qc = useQueryClient()
  const [form, setForm] = useState<FormState>(VACIO)
  //: Dueño elegido, para pintarlo sin volver a consultar. Al crear desde la
  //: ficha de un cliente sólo llega su id, y ese caso lo resuelve `duenoQ`.
  const [dueno, setDueno] = useState<Pick<
    ClienteBrief,
    "id" | "nombre" | "tipo_documento" | "numero_documento"
  > | null>(null)

  // El dueño viene impuesto cuando la bici se registra desde la ficha de un
  // cliente o desde un servicio: cambiarlo ahí crearía la bici a nombre de
  // otro y rompería lo que el formulario de origen espera.
  const duenoFijo = Boolean(clienteId) && !bicicleta

  const duenoQ = useQuery({
    queryKey: ["clientes", clienteId],
    queryFn: async () =>
      (await api.get<ClienteBrief>(`${API_PREFIX}/clientes/${clienteId}`)).data,
    enabled: open && duenoFijo,
  })

  useEffect(() => {
    if (duenoQ.data) setDueno(duenoQ.data)
  }, [duenoQ.data])

  useEffect(() => {
    if (!open) return
    setDueno(bicicleta?.cliente ?? null)
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
      if (bicicleta) {
        await api.patch(`${API_PREFIX}/bicicletas/${bicicleta.id}`, payload)
        return null
      }
      const { data } = await api.post<Bicicleta>(`${API_PREFIX}/bicicletas`, payload)
      return data
    },
    onSuccess: (creada) => {
      qc.invalidateQueries({ queryKey: ["bicicletas"] })
      qc.invalidateQueries({ queryKey: ["clientes"] })
      if (creada) onCreated?.(creada)
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
        <Field
          label="Cliente (dueño)"
          required
          hint={
            dueno || duenoFijo
              ? undefined
              : "Búscalo por nombre o documento; si no está registrado, se da de alta al vuelo."
          }
        >
          {dueno ? (
            <div className="rounded-lg border border-state-success/30 bg-state-success/5 px-3 py-2.5">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="flex items-center gap-1.5 text-sm font-medium">
                    <Check className="h-3.5 w-3.5 shrink-0 text-state-success" />
                    <span className="truncate">{dueno.nombre}</span>
                  </p>
                  <p className="tabular mt-0.5 text-xs text-muted-foreground">
                    {dueno.tipo_documento} {dueno.numero_documento}
                  </p>
                </div>
                {!duenoFijo && (
                  <button
                    type="button"
                    onClick={() => {
                      setDueno(null)
                      set("cliente_id", "")
                    }}
                    className="shrink-0 rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
                    aria-label="Cambiar de dueño"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>
          ) : duenoFijo ? (
            <div className="rounded-lg border border-border px-3 py-2.5 text-sm text-muted-foreground">
              Cargando el cliente…
            </div>
          ) : (
            <BuscarCliente
              onSeleccionar={(c) => {
                setDueno(c)
                set("cliente_id", c.id)
              }}
              placeholder="Buscar el dueño por nombre o documento"
            />
          )}
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
          {/* El dueño ya no es un <select required>, así que el navegador no
              lo exige por su cuenta: sin cliente no hay bici que registrar. */}
          <Button type="submit" disabled={guardar.isPending || !form.cliente_id}>
            {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {bicicleta ? "Guardar cambios" : "Registrar bicicleta"}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
