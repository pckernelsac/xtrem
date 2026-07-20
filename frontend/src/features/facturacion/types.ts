export type TipoComprobante = "FACTURA" | "BOLETA" | "NOTA_CREDITO"
export type EstadoComprobante =
  | "PENDIENTE"
  | "REGISTRADO"
  | "ACEPTADO"
  | "RECHAZADO"
  | "ANULADO"
  | "ERROR"

type Tone = "success" | "warning" | "danger" | "neutral" | "info"

// Colores del patrón de referencia de FactPro: verde=aceptado, gris=registrado,
// rojo=anulado/rechazado, ámbar=pendiente.
export const ESTADOS_COMPROBANTE: { value: EstadoComprobante; label: string; tone: Tone }[] = [
  { value: "PENDIENTE", label: "Pendiente", tone: "warning" },
  { value: "REGISTRADO", label: "Registrado", tone: "neutral" },
  { value: "ACEPTADO", label: "Aceptado", tone: "success" },
  { value: "RECHAZADO", label: "Rechazado", tone: "danger" },
  { value: "ANULADO", label: "Anulado", tone: "danger" },
  { value: "ERROR", label: "Error", tone: "danger" },
]

export const ESTADO_COMP_INFO = Object.fromEntries(
  ESTADOS_COMPROBANTE.map((e) => [e.value, e]),
) as Record<EstadoComprobante, (typeof ESTADOS_COMPROBANTE)[number]>

export const TIPO_COMP_LABEL: Record<TipoComprobante, string> = {
  FACTURA: "Factura",
  BOLETA: "Boleta",
  NOTA_CREDITO: "Nota de crédito",
}

export type Comprobante = {
  id: string
  tipo: TipoComprobante
  estado: EstadoComprobante
  serie: string
  numero: number
  numero_completo: string
  fecha_emision: string
  moneda: string
  /** Congelados al emitir; nulos en comprobantes viejos sin venta. */
  base_imponible: string | null
  igv: string | null
  total: string | null
  cliente_tipo_documento: string
  cliente_numero_documento: string
  cliente_denominacion: string
  tipo_estado_sunat: string | null
  descripcion_estado_sunat: string | null
  hash_cpe: string | null
  xml_url: string | null
  pdf_url: string | null
  cdr_url: string | null
  es_simulado: boolean
  mensaje_error: string | null
  motivo_anulacion: string | null
  created_at: string
}

export type ComprobanteDetail = Comprobante & {
  qr: string | null
  venta: { id: string; numero: string; total: string } | null
  usuario: { id: string; full_name: string } | null
  payload_enviado: Record<string, unknown> | null
  respuesta: Record<string, unknown> | null
}

export type ConteoComprobantes = {
  todas: number
  por_estado: Record<EstadoComprobante, number>
  modo_simulacion: boolean
}
