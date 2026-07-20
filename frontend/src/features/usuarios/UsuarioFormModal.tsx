import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { Button, Field, FormError, Input, Select } from "@/components/ui/Form"
import { Modal } from "@/components/ui/Modal"

export type Usuario = {
  id: string
  email: string
  full_name: string
  dni: string | null
  phone: string | null
  is_active: boolean
  role: { id: string; slug: string; name: string }
  last_login_at: string | null
  created_at: string
}

type Rol = { id: string; slug: string; name: string }

type FormState = {
  full_name: string
  email: string
  dni: string
  phone: string
  role_id: string
  is_active: boolean
  password: string
}

const VACIO: FormState = {
  full_name: "",
  email: "",
  dni: "",
  phone: "",
  role_id: "",
  is_active: true,
  password: "",
}

/** El backend exige 8 caracteres; se valida aquí para no gastar un viaje. */
const LARGO_MIN_CLAVE = 8

export function UsuarioFormModal({
  open,
  onClose,
  usuario,
  esYo,
}: {
  open: boolean
  onClose: () => void
  usuario?: Usuario | null
  /** El backend bloquea auto-desactivarse y auto-cambiarse el rol; aquí esos
   *  campos se deshabilitan para no ofrecer algo que va a fallar. */
  esYo?: boolean
}) {
  const qc = useQueryClient()
  const [form, setForm] = useState<FormState>(VACIO)
  const editando = Boolean(usuario)

  const roles = useQuery({
    queryKey: ["roles"],
    queryFn: async () => (await api.get<Rol[]>(`${API_PREFIX}/roles`)).data,
    enabled: open,
  })

  useEffect(() => {
    if (!open) return
    setForm(
      usuario
        ? {
            full_name: usuario.full_name,
            email: usuario.email,
            dni: usuario.dni ?? "",
            phone: usuario.phone ?? "",
            role_id: usuario.role.id,
            is_active: usuario.is_active,
            password: "",
          }
        : VACIO,
    )
  }, [open, usuario])

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }))

  const guardar = useMutation({
    mutationFn: async () => {
      const base = {
        full_name: form.full_name.trim(),
        email: form.email.trim().toLowerCase(),
        dni: form.dni.trim() || null,
        phone: form.phone.trim() || null,
        role_id: form.role_id,
        is_active: form.is_active,
      }

      if (usuario) {
        // La contraseña sólo viaja si se escribió una nueva: mandarla vacía
        // la reemplazaría por algo inválido.
        await api.patch(`${API_PREFIX}/usuarios/${usuario.id}`, {
          ...base,
          ...(form.password ? { password: form.password } : {}),
        })
      } else {
        await api.post(`${API_PREFIX}/usuarios`, { ...base, password: form.password })
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["usuarios"] })
      onClose()
    },
  })

  const claveCorta = form.password.length > 0 && form.password.length < LARGO_MIN_CLAVE
  const puedeGuardar =
    form.full_name.trim().length >= 2 &&
    form.email.trim().length > 0 &&
    form.role_id &&
    !claveCorta &&
    (editando || form.password.length >= LARGO_MIN_CLAVE)

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editando ? "Editar usuario" : "Nuevo usuario"}
      description={editando ? usuario!.email : "Alta de una cuenta del sistema"}
      className="max-w-xl"
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          guardar.mutate()
        }}
        className="space-y-4"
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Nombre completo" required>
            <Input
              required
              minLength={2}
              value={form.full_name}
              onChange={(e) => set("full_name", e.target.value)}
              placeholder="Juan Pérez Quispe"
            />
          </Field>
          <Field label="Correo" required hint="Es el usuario con el que inicia sesión">
            <Input
              required
              type="email"
              value={form.email}
              onChange={(e) => set("email", e.target.value)}
              placeholder="tecnico@zonaxtrema.pe"
            />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="DNI">
            <Input
              value={form.dni}
              onChange={(e) => set("dni", e.target.value)}
              placeholder="43186966"
            />
          </Field>
          <Field label="Teléfono">
            <Input
              value={form.phone}
              onChange={(e) => set("phone", e.target.value)}
              placeholder="969127107"
            />
          </Field>
          <Field
            label="Rol"
            required
            hint={esYo ? "No puedes cambiar tu propio rol" : undefined}
          >
            <Select
              required
              value={form.role_id}
              disabled={esYo}
              onChange={(e) => set("role_id", e.target.value)}
            >
              <option value="">Elige un rol</option>
              {(roles.data ?? []).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <Field
          label={editando ? "Nueva contraseña" : "Contraseña"}
          required={!editando}
          hint={
            editando
              ? "Déjala en blanco para conservar la actual"
              : `Mínimo ${LARGO_MIN_CLAVE} caracteres`
          }
        >
          <Input
            type="password"
            autoComplete="new-password"
            required={!editando}
            minLength={editando ? undefined : LARGO_MIN_CLAVE}
            value={form.password}
            onChange={(e) => set("password", e.target.value)}
            placeholder={editando ? "Sin cambios" : "••••••••"}
          />
        </Field>

        {claveCorta && (
          <p className="text-xs text-state-danger">
            La contraseña debe tener al menos {LARGO_MIN_CLAVE} caracteres.
          </p>
        )}

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.is_active}
            disabled={esYo}
            onChange={(e) => set("is_active", e.target.checked)}
            className="h-4 w-4 rounded border-border"
          />
          <span>
            Cuenta activa
            <span className="ml-1 text-xs text-muted-foreground">
              {esYo
                ? "· no puedes desactivar tu propia cuenta"
                : "· al desactivarla deja de poder entrar, sin perder su historial"}
            </span>
          </span>
        </label>

        <FormError
          message={guardar.isError ? apiErrorMessage(guardar.error, "No se pudo guardar") : null}
        />

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" disabled={guardar.isPending || !puedeGuardar}>
            {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {editando ? "Guardar cambios" : "Crear usuario"}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
