import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Fecha `YYYY-MM-DD` en la zona horaria del navegador.
 *
 * `toISOString().slice(0,10)` parece hacer lo mismo pero da la fecha en UTC:
 * en Lima (UTC−5), a partir de las 7 p. m. devuelve ya el día siguiente, y los
 * rangos «hasta hoy» se corrían un día.
 */
export function fechaLocal(d: Date): string {
  const mes = String(d.getMonth() + 1).padStart(2, "0")
  const dia = String(d.getDate()).padStart(2, "0")
  return `${d.getFullYear()}-${mes}-${dia}`
}
