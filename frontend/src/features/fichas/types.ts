export type EstadoFicha =
  | "RECIBIDA"
  | "EN_REVISION"
  | "ESPERANDO_REPUESTOS"
  | "EN_REPARACION"
  | "LISTA_PARA_ENTREGAR"
  | "ENTREGADA"
  | "CANCELADA"

export type ServicioCodigo =
  | "MANTENIMIENTO_GENERAL"
  | "MANTENIMIENTO_COMPLETO"
  | "AJUSTE_FRENOS"
  | "AJUSTE_CAMBIOS"
  | "LIMPIEZA_LUBRICACION"
  | "CAMBIO_COMPONENTES"
  | "ALINEACION_RUEDAS"
  | "REVISION_SUSPENSION"

type Tone = "success" | "warning" | "danger" | "neutral" | "info"

/** Orden y color de cada estado. El orden refleja el avance real en el taller. */
export const ESTADOS: { value: EstadoFicha; label: string; tone: Tone }[] = [
  { value: "RECIBIDA", label: "Recibida", tone: "neutral" },
  { value: "EN_REVISION", label: "En revisión", tone: "info" },
  { value: "ESPERANDO_REPUESTOS", label: "Esperando repuestos", tone: "warning" },
  { value: "EN_REPARACION", label: "En reparación", tone: "info" },
  { value: "LISTA_PARA_ENTREGAR", label: "Lista para entregar", tone: "success" },
  { value: "ENTREGADA", label: "Entregada", tone: "success" },
  { value: "CANCELADA", label: "Cancelada", tone: "danger" },
]

export const ESTADO_INFO = Object.fromEntries(
  ESTADOS.map((e) => [e.value, e]),
) as Record<EstadoFicha, (typeof ESTADOS)[number]>

/** Estados desde los que ya no se avanza; el backend rechaza cualquier cambio. */
export const ESTADOS_FINALES: EstadoFicha[] = ["ENTREGADA", "CANCELADA"]

/** Las dos columnas replican el checklist de la ficha impresa. */
export const SERVICIOS_COL1: { value: ServicioCodigo; label: string }[] = [
  { value: "MANTENIMIENTO_GENERAL", label: "Mantenimiento general" },
  { value: "MANTENIMIENTO_COMPLETO", label: "Mantenimiento completo" },
  { value: "AJUSTE_FRENOS", label: "Ajuste de frenos" },
  { value: "AJUSTE_CAMBIOS", label: "Ajuste de cambios" },
  { value: "LIMPIEZA_LUBRICACION", label: "Limpieza y lubricación" },
]

export const SERVICIOS_COL2: { value: ServicioCodigo; label: string }[] = [
  { value: "CAMBIO_COMPONENTES", label: "Cambio de componentes" },
  { value: "ALINEACION_RUEDAS", label: "Alineación de ruedas" },
  { value: "REVISION_SUSPENSION", label: "Revisión de suspensión" },
]

export type Repuesto = {
  id: string
  orden: number
  cantidad: string
  descripcion: string
  marca: string | null
  precio_unitario: string
  subtotal: string
  /** Presente sólo si la línea está enlazada al inventario. */
  producto: { id: string; sku: string; nombre: string; stock_actual: string } | null
}

export type UsuarioBrief = { id: string; full_name: string }

export type EstadoLog = {
  estado_anterior: EstadoFicha | null
  estado_nuevo: EstadoFicha
  comentario: string | null
  created_at: string
  usuario: UsuarioBrief | null
}

export type Ficha = {
  id: string
  numero: string
  estado: EstadoFicha
  cliente: {
    id: string
    nombre: string
    tipo_documento: string
    numero_documento: string
    telefono: string | null
    email: string | null
  }
  bicicleta: {
    id: string
    marca: string
    modelo: string | null
    color: string | null
    numero_serie: string | null
    tipo: string
  }
  fecha_recepcion: string
  fecha_entrega: string | null
  tecnico_recepcion: UsuarioBrief | null
  tecnico_responsable: UsuarioBrief | null
  total_repuestos: string
  esta_firmada: boolean
  archivada: boolean
  created_at: string
}

export type FichaDetail = Ficha & {
  codigo_publico: string
  canal_referencia: string | null
  servicios: ServicioCodigo[]
  servicios_labels: string[]
  servicio_otro: string | null
  diagnostico_inicial: string | null
  trabajo_realizado: string | null
  tiempo_invertido_min: number | null
  observaciones: string | null
  garantia_dias: number | null
  tecnico_entrega: UsuarioBrief | null
  firma_cliente: string | null
  firma_cliente_dni: string | null
  firma_tecnico: string | null
  firma_tecnico_dni: string | null
  fecha_firma: string | null
  repuestos: Repuesto[]
  historial_estados: EstadoLog[]
}

export type Conteos = {
  todas: number
  por_estado: Record<EstadoFicha, number>
  archivadas: number
}

export type Compartir = {
  url_pdf: string
  telefono: string | null
  whatsapp_url: string
  mensaje: string
}

export const soles = (v: string | number) =>
  `S/ ${Number(v).toLocaleString("es-PE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

export const tiempoTexto = (min: number | null) => {
  if (!min) return "—"
  const h = Math.floor(min / 60)
  const m = min % 60
  if (h && m) return `${h} h ${m} min`
  return h ? `${h} h` : `${m} min`
}
