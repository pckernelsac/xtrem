import { useEffect, useId, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Search } from "lucide-react"

import { api, API_PREFIX } from "@/lib/api"
import type { Page } from "@/features/clientes/types"
import { cantidad, soles, type Producto } from "@/features/inventario/types"

type Props = {
  onSeleccionar: (p: Producto) => void
  placeholder?: string
  /** Unidades que quedan de verdad para quien busca: el stock del almacén menos
   *  lo que ya se llevó el formulario. Devolver `null` = ítem sin existencias
   *  (un servicio), que se agrega siempre. Por defecto, el stock a secas. */
  disponibleDe?: (p: Producto) => number | null
}

const stockDelAlmacen = (p: Producto) =>
  p.tipo === "SERVICIO" ? null : Number(p.stock_actual)

/**
 * Buscador de productos del inventario con el stock a la vista.
 *
 * El desplegable plano deja de servir en cuanto el almacén crece: hay que
 * cargarlo entero y aun así se busca a ojo. Aquí se consulta al servidor con
 * debounce, como en el punto de venta, y cada sugerencia lleva su existencia
 * para decidir sin salir del formulario.
 */
export function BuscarProducto({ onSeleccionar, placeholder, disponibleDe }: Props) {
  const listaId = useId()
  const [texto, setTexto] = useState("")
  const [busqueda, setBusqueda] = useState("")
  const [abierto, setAbierto] = useState(false)
  const [activa, setActiva] = useState(-1)

  useEffect(() => {
    const t = setTimeout(() => setBusqueda(texto.trim()), 300)
    return () => clearTimeout(t)
  }, [texto])

  const productosQ = useQuery({
    queryKey: ["inventario", "productos", "buscar", busqueda],
    queryFn: async () =>
      (
        await api.get<Page<Producto>>(`${API_PREFIX}/inventario/productos`, {
          params: { search: busqueda, is_active: true, page_size: 8 },
        })
      ).data,
    // Con menos de dos letras la lista sería ruido.
    enabled: busqueda.length >= 2,
  })

  const sugerencias = busqueda.length >= 2 ? (productosQ.data?.items ?? []) : []
  const mostrar = abierto && busqueda.length >= 2

  useEffect(() => {
    setActiva(-1)
  }, [busqueda])

  const elegir = (p: Producto) => {
    onSeleccionar(p)
    // Se limpia tras cada alta: lo normal es agregar varias piezas seguidas y
    // el texto anterior sólo estorba para la siguiente búsqueda.
    setTexto("")
    setBusqueda("")
    setActiva(-1)
    setAbierto(false)
  }

  const disponible = disponibleDe ?? stockDelAlmacen

  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <input
        value={texto}
        onChange={(e) => {
          setTexto(e.target.value)
          setAbierto(true)
        }}
        onFocus={() => setAbierto(true)}
        // El clic sobre una sugerencia se resuelve en onMouseDown, así que al
        // llegar el blur la línea ya se agregó.
        onBlur={() => setAbierto(false)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" && sugerencias.length) {
            e.preventDefault()
            setAbierto(true)
            setActiva((i) => (i + 1) % sugerencias.length)
            return
          }
          if (e.key === "ArrowUp" && sugerencias.length) {
            e.preventDefault()
            setActiva((i) => (i <= 0 ? sugerencias.length - 1 : i - 1))
            return
          }
          if (e.key === "Escape") {
            setAbierto(false)
            setActiva(-1)
            return
          }
          if (e.key === "Enter") {
            // Sin Enter no hay forma de agregar sin soltar el teclado; con una
            // sola coincidencia se agrega ésa aunque no se haya marcado.
            const elegida = activa >= 0 ? sugerencias[activa] : sugerencias[0]
            if (elegida) {
              e.preventDefault()
              elegir(elegida)
            }
          }
        }}
        placeholder={placeholder ?? "Buscar producto del inventario por SKU, nombre o marca"}
        role="combobox"
        aria-expanded={mostrar}
        aria-controls={listaId}
        aria-autocomplete="list"
        className="w-full rounded-md border border-border bg-background py-2 pl-8 pr-3 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
      />

      {mostrar && (
        <ul
          id={listaId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-md border border-border bg-card shadow-lg"
        >
          {sugerencias.map((p, i) => {
            const queda = disponible(p)
            return (
              <li key={p.id} role="option" aria-selected={i === activa}>
                <button
                  type="button"
                  onMouseDown={(e) => {
                    e.preventDefault()
                    elegir(p)
                  }}
                  onMouseEnter={() => setActiva(i)}
                  className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm ${
                    i === activa ? "bg-accent" : ""
                  }`}
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{p.nombre}</span>
                    <span className="tabular block truncate text-xs text-muted-foreground">
                      {p.sku}
                      {p.marca ? ` · ${p.marca}` : ""} ·{" "}
                      {queda === null ? (
                        "servicio, sin stock"
                      ) : queda <= 0 ? (
                        <span className="text-state-danger">sin stock disponible</span>
                      ) : (
                        <>disponible {cantidad(queda)}</>
                      )}
                    </span>
                  </span>
                  <span className="tabular shrink-0 font-medium">{soles(p.precio_venta)}</span>
                </button>
              </li>
            )
          })}
          {sugerencias.length === 0 && (
            <li className="px-3 py-3 text-sm text-muted-foreground">
              {productosQ.isFetching
                ? "Buscando…"
                : `Ningún producto activo coincide con “${busqueda}”`}
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
