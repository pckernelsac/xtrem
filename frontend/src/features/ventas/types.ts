import type { TipoItem } from "@/features/inventario/types"

export type TipoVenta = "VENTA" | "COTIZACION"
export type EstadoVenta = "PENDIENTE" | "CONFIRMADA" | "ANULADA" | "RECHAZADA"
export type MetodoPago = "EFECTIVO" | "YAPE" | "PLIN" | "TRANSFERENCIA" | "TARJETA"

type Tone = "success" | "warning" | "danger" | "neutral" | "info"

export const ESTADOS_VENTA: { value: EstadoVenta; label: string; tone: Tone }[] = [
  { value: "PENDIENTE", label: "Pendiente", tone: "warning" },
  { value: "CONFIRMADA", label: "Confirmada", tone: "success" },
  { value: "ANULADA", label: "Anulada", tone: "danger" },
  { value: "RECHAZADA", label: "Rechazada", tone: "neutral" },
]

export const ESTADO_VENTA_INFO = Object.fromEntries(
  ESTADOS_VENTA.map((e) => [e.value, e]),
) as Record<EstadoVenta, (typeof ESTADOS_VENTA)[number]>

export const METODOS: { value: MetodoPago; label: string; efectivo: boolean }[] = [
  { value: "EFECTIVO", label: "Efectivo", efectivo: true },
  { value: "YAPE", label: "Yape", efectivo: false },
  { value: "PLIN", label: "Plin", efectivo: false },
  { value: "TRANSFERENCIA", label: "Transferencia", efectivo: false },
  { value: "TARJETA", label: "Tarjeta", efectivo: false },
]

export const METODO_LABEL = Object.fromEntries(
  METODOS.map((m) => [m.value, m.label]),
) as Record<MetodoPago, string>

export type ItemVenta = {
  id: string
  orden: number
  producto: {
    id: string
    sku: string
    nombre: string
    tipo: TipoItem
    stock_actual: string
  } | null
  descripcion: string
  cantidad: string
  precio_unitario: string
  descuento: string
  subtotal: string
}

export type Pago = {
  id: string
  metodo: MetodoPago
  monto: string
  referencia: string | null
  created_at: string
}

export type Venta = {
  id: string
  numero: string
  tipo: TipoVenta
  estado: EstadoVenta
  cliente: { id: string; nombre: string; tipo_documento: string; numero_documento: string } | null
  usuario: { id: string; full_name: string } | null
  subtotal: string
  descuento: string
  total: string
  total_pagado: string
  saldo: string
  esta_pagada: boolean
  vencida: boolean
  valido_hasta: string | null
  archivada: boolean
  created_at: string
}

export type VentaDetail = Venta & {
  ficha_id: string | null
  sesion_caja_id: string | null
  notas: string | null
  fecha_anulacion: string | null
  motivo_anulacion: string | null
  items: ItemVenta[]
  pagos: Pago[]
}

export type ConteoVentas = {
  todas: number
  por_estado: Record<EstadoVenta, number>
  archivadas: number
}

// ------------------------------------------------------------------ Caja
export type EstadoCaja = "ABIERTA" | "CERRADA"
export type TipoMovimientoCaja = "INGRESO" | "EGRESO"

export type MovimientoCaja = {
  id: string
  tipo: TipoMovimientoCaja
  metodo: MetodoPago
  monto: string
  concepto: string
  referencia: string | null
  usuario: { id: string; full_name: string } | null
  created_at: string
}

export type Sesion = {
  id: string
  numero: string
  estado: EstadoCaja
  monto_inicial: string
  fecha_apertura: string
  fecha_cierre: string | null
  usuario_apertura: { id: string; full_name: string } | null
  usuario_cierre: { id: string; full_name: string } | null
  monto_declarado: string | null
  monto_esperado: string | null
  diferencia: string | null
  observaciones: string | null
}

export type Arqueo = Sesion & {
  efectivo_esperado: string
  totales: Record<MetodoPago, { ingresos: string; egresos: string }>
  cantidad_ventas: number
  movimientos: MovimientoCaja[]
}

export const soles = (v: string | number | null) =>
  `S/ ${Number(v ?? 0).toLocaleString("es-PE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
