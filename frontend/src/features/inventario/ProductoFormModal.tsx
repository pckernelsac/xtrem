import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ImagePlus, Loader2, Trash2 } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { Button, Field, FormError, Input, Select, Textarea } from "@/components/ui/Form"
import { Modal } from "@/components/ui/Modal"
import {
  TIPOS,
  UNIDADES,
  type Categoria,
  type Producto,
  type TipoItem,
  type UnidadMedida,
} from "./types"

type FormState = {
  tipo: TipoItem
  sku: string
  nombre: string
  descripcion: string
  marca: string
  categoria_id: string
  unidad: UnidadMedida
  stock_inicial: string
  stock_minimo: string
  precio_compra: string
  precio_venta: string
  codigo_barras: string
  ubicacion: string
}

const VACIO: FormState = {
  tipo: "PRODUCTO",
  sku: "",
  nombre: "",
  descripcion: "",
  marca: "",
  categoria_id: "",
  unidad: "UNIDAD",
  stock_inicial: "0",
  stock_minimo: "0",
  precio_compra: "",
  precio_venta: "",
  codigo_barras: "",
  ubicacion: "",
}

export function ProductoFormModal({
  open,
  onClose,
  producto,
}: {
  open: boolean
  onClose: () => void
  producto?: Producto | null
}) {
  const qc = useQueryClient()
  const [form, setForm] = useState<FormState>(VACIO)
  const editando = Boolean(producto)

  // La foto no viaja en el JSON del producto: se sube aparte, después de
  // guardar, porque el endpoint necesita el id del ítem.
  const fotoInput = useRef<HTMLInputElement>(null)
  const [foto, setFoto] = useState<File | null>(null)
  const [fotoPreview, setFotoPreview] = useState<string | null>(null)
  const [quitarFoto, setQuitarFoto] = useState(false)

  const elegirFoto = (archivo: File | null) => {
    if (!archivo) return
    setFoto(archivo)
    setQuitarFoto(false)
    setFotoPreview((previo) => {
      // Cada elección crea un objectURL nuevo; el anterior se libera o queda
      // retenido en memoria hasta recargar la página.
      if (previo?.startsWith("blob:")) URL.revokeObjectURL(previo)
      return URL.createObjectURL(archivo)
    })
  }

  const categoriasQ = useQuery({
    queryKey: ["inventario", "categorias"],
    queryFn: async () =>
      (await api.get<Categoria[]>(`${API_PREFIX}/inventario/categorias`)).data,
    enabled: open,
  })

  useEffect(() => {
    if (!open) return
    setFoto(null)
    setQuitarFoto(false)
    setFotoPreview((previo) => {
      if (previo?.startsWith("blob:")) URL.revokeObjectURL(previo)
      return producto?.foto_url ?? null
    })
    setForm(
      producto
        ? {
            tipo: producto.tipo,
            sku: producto.sku,
            nombre: producto.nombre,
            descripcion: producto.descripcion ?? "",
            marca: producto.marca ?? "",
            categoria_id: producto.categoria_id ?? "",
            unidad: producto.unidad,
            stock_inicial: "0",
            stock_minimo: String(Number(producto.stock_minimo)),
            precio_compra: String(Number(producto.precio_compra)),
            precio_venta: String(Number(producto.precio_venta)),
            codigo_barras: producto.codigo_barras ?? "",
            ubicacion: producto.ubicacion ?? "",
          }
        : VACIO,
    )
  }, [open, producto])

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }))

  const esServicio = form.tipo === "SERVICIO"

  const guardar = useMutation({
    mutationFn: async () => {
      const base = {
        tipo: form.tipo,
        sku: form.sku,
        nombre: form.nombre,
        descripcion: form.descripcion.trim() || null,
        marca: form.marca.trim() || null,
        categoria_id: form.categoria_id || null,
        unidad: form.unidad,
        // Un servicio no tiene existencias: el backend también lo normaliza,
        // pero así no se manda un mínimo fantasma que el formulario ni muestra.
        stock_minimo: esServicio ? 0 : Number(form.stock_minimo) || 0,
        precio_compra: Number(form.precio_compra) || 0,
        precio_venta: Number(form.precio_venta) || 0,
        codigo_barras: form.codigo_barras.trim() || null,
        ubicacion: form.ubicacion.trim() || null,
      }
      let id = producto?.id
      if (producto) {
        await api.patch(`${API_PREFIX}/inventario/productos/${producto.id}`, base)
      } else {
        const { data } = await api.post<Producto>(`${API_PREFIX}/inventario/productos`, {
          ...base,
          stock_inicial: esServicio ? 0 : Number(form.stock_inicial) || 0,
        })
        id = data.id
      }

      // La foto va al final: si falla la subida, el ítem ya quedó guardado y
      // el error que se muestra es sólo el de la imagen.
      if (foto && id) {
        const cuerpo = new FormData()
        cuerpo.append("archivo", foto)
        await api.put(`${API_PREFIX}/inventario/productos/${id}/foto`, cuerpo, {
          headers: { "Content-Type": "multipart/form-data" },
        })
      } else if (quitarFoto && id && producto?.foto_url) {
        await api.delete(`${API_PREFIX}/inventario/productos/${id}/foto`)
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["inventario"] })
      onClose()
    },
  })

  const margen =
    Number(form.precio_compra) > 0
      ? ((Number(form.precio_venta) - Number(form.precio_compra)) /
          Number(form.precio_compra)) *
        100
      : null

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={
        editando
          ? esServicio
            ? "Editar servicio"
            : "Editar producto"
          : esServicio
            ? "Nuevo servicio"
            : "Nuevo producto"
      }
      description={
        editando
          ? producto!.nombre
          : esServicio
            ? "Alta de un trabajo de taller que se puede vender o cotizar"
            : "Alta de producto en el almacén"
      }
      className="max-w-2xl"
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          guardar.mutate()
        }}
        className="space-y-4"
      >
        {/* El tipo va primero porque decide qué campos tienen sentido debajo. */}
        <Field label="Tipo" hint={TIPOS.find((t) => t.value === form.tipo)!.ayuda}>
          <div className="flex gap-2">
            {TIPOS.map((t) => (
              <button
                key={t.value}
                type="button"
                onClick={() => set("tipo", t.value)}
                aria-pressed={form.tipo === t.value}
                className={`flex-1 rounded-md border px-3 py-2 text-sm font-medium transition-colors ${
                  form.tipo === t.value
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:bg-accent"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </Field>

        <Field
          label="Foto"
          hint="JPG, PNG o WEBP. Se reescala a 800 px al guardarla."
        >
          <div className="flex items-center gap-3">
            <div className="flex h-24 w-24 shrink-0 items-center justify-center overflow-hidden rounded-md border border-border bg-muted/40">
              {fotoPreview ? (
                <img src={fotoPreview} alt="" className="h-full w-full object-cover" />
              ) : (
                <ImagePlus className="h-6 w-6 text-muted-foreground" />
              )}
            </div>
            <div className="flex flex-col gap-2">
              <input
                ref={fotoInput}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                onChange={(e) => elegirFoto(e.target.files?.[0] ?? null)}
              />
              <Button
                type="button"
                variant="secondary"
                onClick={() => fotoInput.current?.click()}
              >
                <ImagePlus className="h-4 w-4" />
                {fotoPreview ? "Cambiar foto" : "Subir foto"}
              </Button>
              {fotoPreview && (
                <button
                  type="button"
                  onClick={() => {
                    setFoto(null)
                    setFotoPreview(null)
                    setQuitarFoto(true)
                    if (fotoInput.current) fotoInput.current.value = ""
                  }}
                  className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-state-danger"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Quitar foto
                </button>
              )}
            </div>
          </div>
        </Field>

        <div className="grid gap-4 sm:grid-cols-[160px_1fr]">
          <Field label="SKU" required hint="Se guarda en mayúsculas y sin espacios">
            <Input
              required
              value={form.sku}
              onChange={(e) => set("sku", e.target.value)}
              placeholder={esServicio ? "SERV-AFIN" : "CAD-XT-12V"}
            />
          </Field>
          <Field label="Nombre" required>
            <Input
              required
              minLength={2}
              value={form.nombre}
              onChange={(e) => set("nombre", e.target.value)}
              placeholder={esServicio ? "Afinamiento completo" : "Cadena 12v XT M8100"}
            />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Marca">
            <Input
              value={form.marca}
              onChange={(e) => set("marca", e.target.value)}
              placeholder="Shimano"
            />
          </Field>
          <Field label="Categoría">
            <Select
              value={form.categoria_id}
              onChange={(e) => set("categoria_id", e.target.value)}
            >
              <option value="">Sin categoría</option>
              {(categoriasQ.data ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nombre}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Unidad">
            <Select
              value={form.unidad}
              onChange={(e) => set("unidad", e.target.value as UnidadMedida)}
            >
              {UNIDADES.map((u) => (
                <option key={u.value} value={u.value}>
                  {u.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        {/* Stock y ubicación sólo aplican a lo que ocupa un estante. */}
        <div className="grid gap-4 sm:grid-cols-3">
          {!esServicio && !editando && (
            <Field label="Stock inicial" hint="Queda registrado en el kardex">
              <Input
                type="number"
                min="0"
                step="0.001"
                value={form.stock_inicial}
                onChange={(e) => set("stock_inicial", e.target.value)}
              />
            </Field>
          )}
          {!esServicio && (
            <>
              <Field label="Stock mínimo" hint="0 = sin alerta">
                <Input
                  type="number"
                  min="0"
                  step="0.001"
                  value={form.stock_minimo}
                  onChange={(e) => set("stock_minimo", e.target.value)}
                />
              </Field>
              <Field label="Ubicación">
                <Input
                  value={form.ubicacion}
                  onChange={(e) => set("ubicacion", e.target.value)}
                  placeholder="Estante A-3"
                />
              </Field>
            </>
          )}
          {editando && (
            <Field label="Código de barras">
              <Input
                value={form.codigo_barras}
                onChange={(e) => set("codigo_barras", e.target.value)}
              />
            </Field>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Precio de compra">
            <Input
              type="number"
              min="0"
              step="0.01"
              value={form.precio_compra}
              onChange={(e) => set("precio_compra", e.target.value)}
              placeholder="0.00"
            />
          </Field>
          <Field label="Precio de venta">
            <Input
              type="number"
              min="0"
              step="0.01"
              value={form.precio_venta}
              onChange={(e) => set("precio_venta", e.target.value)}
              placeholder="0.00"
            />
          </Field>
          <div className="flex items-end pb-1">
            {margen !== null && (
              <p className="text-sm">
                <span className="text-xs text-muted-foreground">Margen </span>
                <span
                  className={
                    margen >= 0 ? "tabular font-semibold text-state-success" : "tabular font-semibold text-state-danger"
                  }
                >
                  {margen.toFixed(1)}%
                </span>
              </p>
            )}
          </div>
        </div>

        {!editando && (
          <Field label="Código de barras">
            <Input
              value={form.codigo_barras}
              onChange={(e) => set("codigo_barras", e.target.value)}
              placeholder="7891234567890"
            />
          </Field>
        )}

        <Field label="Descripción">
          <Textarea
            rows={2}
            value={form.descripcion}
            onChange={(e) => set("descripcion", e.target.value)}
          />
        </Field>

        {editando && !esServicio && (
          <p className="text-xs text-muted-foreground">
            El stock no se edita aquí: se mueve con entradas, salidas o ajustes para que quede
            registrado en el kardex.
          </p>
        )}
        {esServicio && (
          <p className="text-xs text-muted-foreground">
            Un servicio no lleva stock ni kardex: se puede vender siempre, sin importar las
            existencias.
          </p>
        )}

        <FormError
          message={guardar.isError ? apiErrorMessage(guardar.error, "No se pudo guardar") : null}
        />

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" disabled={guardar.isPending}>
            {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {editando ? "Guardar cambios" : esServicio ? "Crear servicio" : "Crear producto"}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
