export type TipoDocumento = "DNI" | "RUC" | "CE" | "PASAPORTE"

export type TipoBicicleta =
  | "MTB"
  | "RUTA"
  | "URBANA"
  | "BMX"
  | "PLEGABLE"
  | "ELECTRICA"
  | "INFANTIL"
  | "OTRA"

export const TIPOS_DOCUMENTO: TipoDocumento[] = ["DNI", "RUC", "CE", "PASAPORTE"]

export const TIPOS_BICICLETA: { value: TipoBicicleta; label: string }[] = [
  { value: "MTB", label: "Montañera (MTB)" },
  { value: "RUTA", label: "Ruta" },
  { value: "URBANA", label: "Urbana" },
  { value: "BMX", label: "BMX" },
  { value: "PLEGABLE", label: "Plegable" },
  { value: "ELECTRICA", label: "Eléctrica" },
  { value: "INFANTIL", label: "Infantil" },
  { value: "OTRA", label: "Otra" },
]

export type BicicletaBrief = {
  id: string
  marca: string
  modelo: string | null
  color: string | null
  numero_serie: string | null
  tipo: string
  is_active: boolean
}

export type Cliente = {
  id: string
  nombre: string
  tipo_documento: TipoDocumento
  numero_documento: string
  telefono: string | null
  email: string | null
  direccion: string | null
  notas: string | null
  is_active: boolean
  created_at: string
  bicicletas_count: number
}

export type ClienteDetail = Cliente & { bicicletas: BicicletaBrief[] }

export type ClienteBrief = {
  id: string
  nombre: string
  tipo_documento: string
  numero_documento: string
  telefono: string | null
}

export type Bicicleta = {
  id: string
  cliente_id: string
  cliente: ClienteBrief
  marca: string
  modelo: string | null
  color: string | null
  numero_serie: string | null
  tipo: TipoBicicleta
  rodado: string | null
  talla: string | null
  anio: number | null
  notas: string | null
  is_active: boolean
  descripcion: string
  created_at: string
}

export type EventoHistorial = {
  fecha: string
  tipo: string
  titulo: string
  detalle: string | null
}

export type BicicletaDetail = Bicicleta & { historial: EventoHistorial[] }

export type Page<T> = { items: T[]; total: number; page: number; page_size: number }

export const fmtFecha = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleDateString("es-PE", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      })
    : "—"

export const fmtFechaHora = (iso: string) =>
  new Date(iso).toLocaleString("es-PE", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
