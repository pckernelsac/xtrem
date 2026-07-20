export type TipoItem = "PRODUCTO" | "SERVICIO"
export type UnidadMedida = "UNIDAD" | "PAR" | "JUEGO" | "METRO" | "LITRO" | "KIT"

export const TIPOS: { value: TipoItem; label: string; ayuda: string }[] = [
  {
    value: "PRODUCTO",
    label: "Producto",
    ayuda: "Pieza física del almacén: lleva stock, kardex y alertas de reposición.",
  },
  {
    value: "SERVICIO",
    label: "Servicio",
    ayuda: "Mano de obra o trabajo de taller: se vende y cotiza, pero no tiene stock.",
  },
]
export type TipoMovimiento = "ENTRADA" | "SALIDA" | "AJUSTE"

export const UNIDADES: { value: UnidadMedida; label: string }[] = [
  { value: "UNIDAD", label: "Unidad" },
  { value: "PAR", label: "Par" },
  { value: "JUEGO", label: "Juego" },
  { value: "METRO", label: "Metro" },
  { value: "LITRO", label: "Litro" },
  { value: "KIT", label: "Kit" },
]

export const MOVIMIENTOS: {
  value: TipoMovimiento
  label: string
  tone: "success" | "danger" | "warning"
  ayuda: string
}[] = [
  {
    value: "ENTRADA",
    label: "Entrada",
    tone: "success",
    ayuda: "Compra a proveedor o devolución de un cliente. Suma al stock.",
  },
  {
    value: "SALIDA",
    label: "Salida",
    tone: "danger",
    ayuda: "Venta, consumo en taller o merma. Resta del stock.",
  },
  {
    value: "AJUSTE",
    label: "Ajuste",
    tone: "warning",
    ayuda: "Conteo físico. Escribe el stock que contaste, no la diferencia.",
  },
]

export type Categoria = {
  id: string
  nombre: string
  descripcion: string | null
  is_active: boolean
  productos_count: number
}

export type Producto = {
  id: string
  tipo: TipoItem
  sku: string
  nombre: string
  descripcion: string | null
  marca: string | null
  categoria_id: string | null
  categoria: { id: string; nombre: string } | null
  unidad: UnidadMedida
  stock_actual: string
  stock_minimo: string
  precio_compra: string
  precio_venta: string
  codigo_barras: string | null
  ubicacion: string | null
  /** Ruta relativa ya versionada (`?v=`), servida sin token. */
  foto_url: string | null
  is_active: boolean
  bajo_minimo: boolean
  sin_stock: boolean
  valor_stock: string
  margen: string | null
  created_at: string
}

export type Movimiento = {
  id: string
  producto: { id: string; sku: string; nombre: string; unidad: UnidadMedida }
  tipo: TipoMovimiento
  cantidad: string
  stock_anterior: string
  stock_posterior: string
  costo_unitario: string | null
  motivo: string | null
  referencia: string | null
  usuario: { id: string; full_name: string } | null
  created_at: string
}

export type Resumen = {
  productos_activos: number
  servicios_activos: number
  archivados: number
  bajo_minimo: number
  sin_stock: number
  valor_total: string
}

export type FilaImportacion = {
  fila: number
  sku: string | null
  accion: "creado" | "actualizado" | "error" | "omitido"
  detalle: string | null
}

export type ResultadoImportacion = {
  modo_prueba: boolean
  total_filas: number
  creados: number
  actualizados: number
  errores: number
  filas: FilaImportacion[]
}

/** Los decimales llegan como string desde el backend para no perder precisión. */
export const num = (v: string | number | null) => Number(v ?? 0)

export const cantidad = (v: string | number) => {
  const n = Number(v)
  // 12.000 -> "12"; 2.500 -> "2.5". El almacén no lee ceros de relleno.
  return n.toLocaleString("es-PE", { maximumFractionDigits: 3 })
}

export const soles = (v: string | number | null) =>
  `S/ ${num(v).toLocaleString("es-PE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
