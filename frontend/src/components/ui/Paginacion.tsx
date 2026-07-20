import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react"

import { cn } from "@/lib/utils"

type Props = {
  /** Página actual, empezando en 1. */
  page: number
  /** Filas por página, para calcular el total de páginas y el rango visible. */
  pageSize: number
  /** Total de filas que hay en el servidor, no las de esta página. */
  total: number
  onChange: (page: number) => void
  /** Sustantivo en plural que se muestra junto al total: «… · 128 clientes». */
  etiqueta: string
  /** Forma singular, para no escribir «1 jornadas». Si no se pasa, se usa
   *  `etiqueta` sin la «s» final, que cubre todos los casos del sistema. */
  singular?: string
  /** Variante chica para pies de panel, como el catálogo del punto de venta. */
  compacta?: boolean
  className?: string
}

/** Cuántos números de página se muestran alrededor del actual. */
const VENTANA = 2

/**
 * Devuelve los números a pintar, con `null` donde va un salto («…»).
 *
 * Siempre incluye la primera y la última página: son los dos saltos que más se
 * usan, y así el ancho de la barra no baila al moverse por el medio.
 */
function numerosVisibles(page: number, totalPages: number): (number | null)[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1)
  }

  const nums = new Set<number>([1, totalPages])
  for (let p = page - VENTANA; p <= page + VENTANA; p++) {
    if (p >= 1 && p <= totalPages) nums.add(p)
  }

  const ordenados = [...nums].sort((a, b) => a - b)
  const salida: (number | null)[] = []
  ordenados.forEach((n, i) => {
    if (i > 0 && n - ordenados[i - 1] > 1) salida.push(null)
    salida.push(n)
  })
  return salida
}

/**
 * Pie de paginación de las listas.
 *
 * La barra se dibuja siempre que haya filas, aunque quepan en una sola página:
 * el conteo («128 clientes») es información útil por sí misma, y los controles
 * en su sitio —deshabilitados— evitan que la tabla salte al filtrar. Con la
 * lista vacía no se dibuja: ahí manda el mensaje de «sin resultados».
 */
export function Paginacion({
  page,
  pageSize,
  total,
  onChange,
  etiqueta,
  singular,
  compacta = false,
  className,
}: Props) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  if (total === 0) return null

  const nombre = total === 1 ? (singular ?? etiqueta.replace(/s$/, "")) : etiqueta

  // Rango real de esta página: la última suele estar incompleta.
  const desde = (page - 1) * pageSize + 1
  const hasta = Math.min(page * pageSize, total)

  const irA = (p: number) => onChange(Math.min(totalPages, Math.max(1, p)))

  const btn = cn(
    "inline-flex items-center justify-center rounded-md border border-border transition",
    "hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent",
    compacta ? "h-7 min-w-7 px-1.5 text-xs" : "h-8 min-w-8 px-2 text-sm",
  )

  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-x-4 gap-y-2",
        compacta
          ? "shrink-0 border-t border-border px-3 py-2 text-xs text-muted-foreground"
          : "mt-3 text-sm",
        className,
      )}
    >
      <span className={compacta ? undefined : "text-muted-foreground"}>
        {totalPages > 1 ? (
          <>
            <span className="tabular">{desde}</span>–<span className="tabular">{hasta}</span> de{" "}
            <span className="tabular">{total}</span> {nombre}
          </>
        ) : (
          <>
            <span className="tabular">{total}</span> {nombre}
          </>
        )}
      </span>

      <div className="flex items-center gap-1">
        <button
          type="button"
          className={btn}
          disabled={page <= 1}
          onClick={() => irA(1)}
          title="Primera página"
          aria-label="Ir a la primera página"
        >
          <ChevronsLeft className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          className={btn}
          disabled={page <= 1}
          onClick={() => irA(page - 1)}
          aria-label="Página anterior"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          <span className={compacta ? "sr-only" : "ml-0.5 mr-1 hidden sm:inline"}>Anterior</span>
        </button>

        {numerosVisibles(page, totalPages).map((n, i) =>
          n === null ? (
            <span key={`salto-${i}`} className="px-1 text-muted-foreground">
              …
            </span>
          ) : (
            <button
              key={n}
              type="button"
              className={cn(
                btn,
                "tabular",
                n === page && "border-primary bg-primary font-semibold text-white hover:bg-primary",
              )}
              aria-current={n === page ? "page" : undefined}
              aria-label={`Ir a la página ${n}`}
              onClick={() => irA(n)}
            >
              {n}
            </button>
          ),
        )}

        <button
          type="button"
          className={btn}
          disabled={page >= totalPages}
          onClick={() => irA(page + 1)}
          aria-label="Página siguiente"
        >
          <span className={compacta ? "sr-only" : "ml-1 mr-0.5 hidden sm:inline"}>Siguiente</span>
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          className={btn}
          disabled={page >= totalPages}
          onClick={() => irA(totalPages)}
          title="Última página"
          aria-label="Ir a la última página"
        >
          <ChevronsRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}

/**
 * Recorta en el cliente una lista que ya vino entera del servidor.
 *
 * Para los bloques anidados de las páginas de detalle (las bicicletas de un
 * cliente, el historial de una bici): el endpoint devuelve el detalle completo
 * en una sola respuesta, así que no hay nada que pedir al paginar.
 */
export function recortarPagina<T>(items: T[], page: number, pageSize: number): T[] {
  return items.slice((page - 1) * pageSize, page * pageSize)
}
