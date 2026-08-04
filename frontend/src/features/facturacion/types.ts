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

export type CompartirComprobante = {
  url_pdf: string
  telefono: string | null
  whatsapp_url: string
  mensaje: string
}

// ---------------------------------------------------------------- Lotes SUNAT
// Emitir una boleta no la declara: SUNAT sólo la da por informada cuando llega
// en un resumen diario, y hay plazo para mandarlo.
export type TipoLote = "RC" | "RA"
export type EstadoLote = "PENDIENTE" | "ENVIADO" | "ACEPTADO" | "RECHAZADO" | "ERROR"

export const ESTADO_LOTE_INFO: Record<EstadoLote, { label: string; tone: Tone }> = {
  PENDIENTE: { label: "Pendiente", tone: "warning" },
  // "En proceso" y no "Enviado": describe mejor lo que pasa, que es que SUNAT
  // lo está procesando y el CDR todavía no ha llegado.
  ENVIADO: { label: "En proceso", tone: "info" },
  ACEPTADO: { label: "Aceptado", tone: "success" },
  RECHAZADO: { label: "Rechazado", tone: "danger" },
  ERROR: { label: "Error", tone: "danger" },
}

export const TIPO_LOTE_LABEL: Record<TipoLote, string> = {
  RC: "Resumen de boletas",
  RA: "Comunicación de baja",
}

export type Lote = {
  id: string
  tipo: TipoLote
  estado: EstadoLote
  identificador: string
  fecha_referencia: string
  fecha_emision: string
  ticket: string | null
  codigo_sunat: string | null
  descripcion_sunat: string | null
  mensaje_error: string | null
  es_simulado: boolean
  cantidad: number
  pendiente_de_cdr: boolean
  created_at: string
}

export type DiaPendiente = {
  fecha: string
  boletas: number
  total: string | null
  dias_transcurridos: number
  /** Pasado el plazo de SUNAT deja de ser un olvido y pasa a ser un problema. */
  fuera_de_plazo: boolean
}
