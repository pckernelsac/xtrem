export type TipoComprobante = "FACTURA" | "BOLETA" | "NOTA_CREDITO"
export type EstadoComprobante =
  | "PENDIENTE"
  | "REGISTRADO"
  | "ACEPTADO"
  | "RECHAZADO"
  | "ANULADO"
  | "ERROR"

export type Tone = "success" | "warning" | "danger" | "neutral" | "info"

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
  /** Código del enlace público del PDF (/c/{codigo}). */
  codigo_publico: string
  /** Qué archivos existen de verdad. El PDF se genera siempre. */
  tiene_xml: boolean
  tiene_cdr: boolean
  es_simulado: boolean
  /**
   * Emitido, pero SUNAT no llegó a recibirlo porque estaba caído. Se reenvía
   * solo con el mismo número: no hay que volver a emitirlo, o la serie
   * acabaría con dos documentos para el mismo correlativo.
   */
  envio_pendiente: boolean
  intentos_envio: number
  mensaje_error: string | null
  motivo_anulacion: string | null
  created_at: string
}

/**
 * Etiqueta y color con los que se pinta el estado de un comprobante.
 *
 * La descripción de SUNAT manda cuando existe: dice bastante más que el estado
 * interno. El único matiz es la cola de reenvío, que va en ámbar aunque el
 * estado sea `REGISTRADO` —el gris de «registrado» lo daría por resuelto, y lo
 * que hay es un documento que todavía no ha llegado a SUNAT.
 */
export function estadoComprobante(
  c: Pick<Comprobante, "estado" | "descripcion_estado_sunat" | "envio_pendiente">,
): { label: string; tone: Tone } {
  const base = ESTADO_COMP_INFO[c.estado]
  return {
    label: c.descripcion_estado_sunat ?? base.label,
    tone: c.envio_pendiente ? "warning" : base.tone,
  }
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
  /** Emitidos y en cola porque SUNAT no respondió. */
  sin_enviar: number
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
