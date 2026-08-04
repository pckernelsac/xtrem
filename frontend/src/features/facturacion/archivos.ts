import { api, API_PREFIX } from "@/lib/api"

import type { Comprobante } from "./types"

/** Los tres archivos de un comprobante electrónico. */
export type ArchivoComprobante = "pdf" | "xml" | "cdr"

export const ARCHIVO_INFO: Record<
  ArchivoComprobante,
  { label: string; titulo: string }
> = {
  pdf: { label: "PDF", titulo: "Ver la representación impresa" },
  xml: {
    label: "XML",
    titulo: "Descargar el XML firmado (el documento con valor legal)",
  },
  cdr: { label: "CDR", titulo: "Descargar la constancia de recepción de SUNAT" },
}

/** Nombre de archivo con la convención de SUNAT, igual que el del servidor. */
function nombre(c: Comprobante, archivo: ArchivoComprobante): string {
  const base = `${c.serie}-${String(c.numero).padStart(8, "0")}`
  return archivo === "cdr" ? `R-${base}.xml` : `${base}.${archivo}`
}

/**
 * Trae un archivo del comprobante y lo abre o lo guarda.
 *
 * Va por el cliente autenticado y como blob porque una navegación normal no
 * manda la cabecera de sesión: enlazar la URL directamente devolvería un 401.
 *
 * El PDF se genera en el momento —ya no lo aloja nadie más—, así que siempre
 * está disponible. El XML y el CDR salen de la base, y por eso la fila sólo los
 * ofrece cuando existen.
 */
export async function abrirArchivo(
  c: Comprobante,
  archivo: ArchivoComprobante,
): Promise<void> {
  const res = await api.get(`${API_PREFIX}/facturacion/documentos/${c.id}/${archivo}`, {
    responseType: "blob",
  })
  const url = URL.createObjectURL(res.data as Blob)

  if (archivo === "pdf") {
    window.open(url, "_blank")
  } else {
    // El XML y el CDR no se leen en pantalla: son para guardar y para el
    // contador, así que van directos a la carpeta de descargas.
    const a = document.createElement("a")
    a.href = url
    a.download = nombre(c, archivo)
    a.click()
  }

  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
