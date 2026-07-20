import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Loader2, Search } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { Button, Field, FormError, Input, Select, Textarea } from "@/components/ui/Form"
import { Modal } from "@/components/ui/Modal"
import { TIPOS_DOCUMENTO, type Cliente, type TipoDocumento } from "./types"

// Longitudes que exige el backend; las replicamos para dar pista al usuario
// antes de enviar. La validación real vive en el servidor.
const AYUDA_DOC: Record<TipoDocumento, string> = {
  DNI: "8 dígitos",
  RUC: "11 dígitos",
  CE: "9 a 12 caracteres",
  PASAPORTE: "6 a 12 caracteres",
}

type FormState = {
  nombre: string
  tipo_documento: TipoDocumento
  numero_documento: string
  telefono: string
  email: string
  direccion: string
  notas: string
}

const VACIO: FormState = {
  nombre: "",
  tipo_documento: "DNI",
  numero_documento: "",
  telefono: "",
  email: "",
  direccion: "",
  notas: "",
}

export function ClienteFormModal({
  open,
  onClose,
  cliente,
}: {
  open: boolean
  onClose: () => void
  cliente?: Cliente | null
}) {
  const qc = useQueryClient()
  const [form, setForm] = useState<FormState>(VACIO)

  useEffect(() => {
    if (!open) return
    setForm(
      cliente
        ? {
            nombre: cliente.nombre,
            tipo_documento: cliente.tipo_documento,
            numero_documento: cliente.numero_documento,
            telefono: cliente.telefono ?? "",
            email: cliente.email ?? "",
            direccion: cliente.direccion ?? "",
            notas: cliente.notas ?? "",
          }
        : VACIO,
    )
  }, [open, cliente])

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }))

  // ¿Está configurada la consulta RENIEC/SUNAT? Si no, no se muestra el botón.
  const consultaDisponible = useQuery({
    queryKey: ["clientes", "consulta-disponible"],
    queryFn: async () =>
      (await api.get<{ disponible: boolean }>(`${API_PREFIX}/clientes/consulta-documento/disponible`))
        .data.disponible,
    enabled: open,
    staleTime: 5 * 60_000,
  })

  const consultar = useMutation({
    mutationFn: async () => {
      const { data } = await api.get<{ nombre: string; direccion: string | null }>(
        `${API_PREFIX}/clientes/consulta-documento`,
        { params: { tipo: form.tipo_documento, numero: form.numero_documento } },
      )
      return data
    },
    onSuccess: (data) => {
      // Trae el nombre desde el padrón; la dirección sólo la da SUNAT (RUC).
      setForm((f) => ({
        ...f,
        nombre: data.nombre,
        direccion: data.direccion ?? f.direccion,
      }))
    },
  })

  const largoOk =
    (form.tipo_documento === "DNI" && form.numero_documento.length === 8) ||
    (form.tipo_documento === "RUC" && form.numero_documento.length === 11)
  const puedeConsultar =
    consultaDisponible.data &&
    (form.tipo_documento === "DNI" || form.tipo_documento === "RUC")

  const guardar = useMutation({
    mutationFn: async () => {
      // Los opcionales vacíos van como null, no como "": el backend valida
      // formato de correo y un string vacío fallaría la validación.
      const payload = {
        nombre: form.nombre,
        tipo_documento: form.tipo_documento,
        numero_documento: form.numero_documento,
        telefono: form.telefono.trim() || null,
        email: form.email.trim() || null,
        direccion: form.direccion.trim() || null,
        notas: form.notas.trim() || null,
      }
      if (cliente) await api.patch(`${API_PREFIX}/clientes/${cliente.id}`, payload)
      else await api.post(`${API_PREFIX}/clientes`, payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["clientes"] })
      onClose()
    },
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={cliente ? "Editar cliente" : "Nuevo cliente"}
      description={cliente ? cliente.nombre : "Registra los datos de contacto del cliente"}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          guardar.mutate()
        }}
        className="space-y-4"
      >
        {/* El documento va primero: se ingresa, se busca, y el nombre aparece
            debajo como resultado de la consulta. */}
        <div className="grid gap-4 sm:grid-cols-[130px_1fr]">
          <Field label="Tipo de doc." required>
            <Select
              value={form.tipo_documento}
              onChange={(e) => set("tipo_documento", e.target.value as TipoDocumento)}
            >
              {TIPOS_DOCUMENTO.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
          </Field>

          <Field
            label="Número de documento"
            required
            hint={
              puedeConsultar
                ? `${AYUDA_DOC[form.tipo_documento]} · busca el nombre en ${
                    form.tipo_documento === "DNI" ? "RENIEC" : "SUNAT"
                  }`
                : AYUDA_DOC[form.tipo_documento]
            }
          >
            <div className="flex gap-2">
              <Input
                required
                value={form.numero_documento}
                onChange={(e) => set("numero_documento", e.target.value)}
                placeholder={form.tipo_documento === "RUC" ? "20601234567" : "45678912"}
              />
              {puedeConsultar && (
                <Button
                  type="button"
                  variant="secondary"
                  className="shrink-0"
                  disabled={!largoOk || consultar.isPending}
                  onClick={() => consultar.mutate()}
                  title={
                    largoOk
                      ? "Buscar el nombre por el documento"
                      : `Ingresa el ${form.tipo_documento} completo`
                  }
                >
                  {consultar.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Search className="h-4 w-4" />
                  )}
                  Buscar
                </Button>
              )}
            </div>
          </Field>
        </div>

        {consultar.isError && (
          <p className="-mt-2 text-xs text-state-danger">
            {apiErrorMessage(consultar.error, "No se pudo consultar el documento")}
          </p>
        )}

        <Field
          label="Nombre completo o razón social"
          required
          hint={
            consultar.isSuccess
              ? `Traído de ${form.tipo_documento === "RUC" ? "SUNAT" : "RENIEC"}; puedes corregirlo`
              : undefined
          }
        >
          <Input
            required
            minLength={2}
            value={form.nombre}
            onChange={(e) => set("nombre", e.target.value)}
            placeholder="Rosa Quispe Mamani"
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Teléfono">
            <Input
              value={form.telefono}
              onChange={(e) => set("telefono", e.target.value)}
              placeholder="987654321"
            />
          </Field>
          <Field label="Correo">
            <Input
              type="email"
              value={form.email}
              onChange={(e) => set("email", e.target.value)}
              placeholder="cliente@correo.com"
            />
          </Field>
        </div>

        <Field label="Dirección">
          <Input
            value={form.direccion}
            onChange={(e) => set("direccion", e.target.value)}
            placeholder="Av. Perú 123, Lima"
          />
        </Field>

        <Field label="Notas internas">
          <Textarea
            rows={2}
            value={form.notas}
            onChange={(e) => set("notas", e.target.value)}
            placeholder="Preferencias, acuerdos, observaciones..."
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
            {cliente ? "Guardar cambios" : "Crear cliente"}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
