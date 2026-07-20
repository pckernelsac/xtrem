import { useEffect, useMemo, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams } from "react-router-dom"
import {
  AlertTriangle,
  FileText,
  ImageOff,
  Loader2,
  Minus,
  Plus,
  ScanLine,
  ShoppingCart,
  Trash2,
  Wallet,
} from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { Badge } from "@/components/ui/Badge"
import { Button, Field, FormError, Input, Select, Textarea } from "@/components/ui/Form"
import { PageHeader } from "@/components/ui/PageHeader"
import { Paginacion } from "@/components/ui/Paginacion"
import { BuscarClienteDocumento } from "@/features/clientes/BuscarClienteDocumento"
import type { Cliente, Page } from "@/features/clientes/types"
import {
  cantidad,
  type Categoria,
  type Producto,
  type TipoItem,
} from "@/features/inventario/types"
import { PagoModal, type LineaPago } from "@/features/ventas/PagoModal"
import { soles, type Arqueo, type VentaDetail } from "@/features/ventas/types"

/** El catálogo ocupa toda la columna izquierda y se desplaza dentro de su
 *  panel, así que caben más tarjetas por página que en una lista suelta. */
const CATALOGO_PAGE_SIZE = 24

type Linea = {
  producto_id: string | null
  sku: string | null
  descripcion: string
  cantidad: string
  precio_unitario: string
  descuento: string
  stock: number | null
}

export default function PuntoVentaPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const scanRef = useRef<HTMLInputElement>(null)
  const carritoRef = useRef<HTMLDivElement>(null)

  // La ruta /ventas/:id/editar reutiliza esta pantalla para retocar una
  // cotización pendiente antes de convertirla.
  const { id: editId } = useParams()
  const editando = Boolean(editId)

  const [codigo, setCodigo] = useState("")
  const [lineas, setLineas] = useState<Linea[]>([])
  const [clienteId, setClienteId] = useState("")
  const [descuento, setDescuento] = useState("")
  const [notas, setNotas] = useState("")
  const [pagoOpen, setPagoOpen] = useState(false)
  const [errorScan, setErrorScan] = useState<string | null>(null)

  // Autocompletado por nombre: el mostrador no siempre tiene el código a mano
  // (repuestos sueltos, productos sin etiqueta) y busca "cadena", "parche"...
  const [busqueda, setBusqueda] = useState("")
  const [sugerenciasOpen, setSugerenciasOpen] = useState(false)
  const [activa, setActiva] = useState(-1)

  useEffect(() => {
    const t = setTimeout(() => setBusqueda(codigo.trim()), 300)
    return () => clearTimeout(t)
  }, [codigo])

  const caja = useQuery({
    queryKey: ["caja", "actual"],
    queryFn: async () => (await api.get<Arqueo | null>(`${API_PREFIX}/caja/actual`)).data,
  })

  const clientes = useQuery({
    queryKey: ["clientes", "activos-select"],
    queryFn: async () =>
      (
        await api.get<Page<Cliente>>(`${API_PREFIX}/clientes`, {
          params: { is_active: true, page_size: 200 },
        })
      ).data,
  })

  // ---------------- Catálogo en cuadrícula ----------------
  // El mostrador con pantalla táctil no siempre teclea: elegir por foto es más
  // rápido para lo que se vende a diario y para el cliente que señala.
  const [catTipo, setCatTipo] = useState<"" | TipoItem>("")
  const [catCategoria, setCatCategoria] = useState("")
  const [catPage, setCatPage] = useState(1)

  useEffect(() => {
    setCatPage(1)
  }, [busqueda, catTipo, catCategoria])

  const categoriasQ = useQuery({
    queryKey: ["inventario", "categorias"],
    queryFn: async () =>
      (await api.get<Categoria[]>(`${API_PREFIX}/inventario/categorias`)).data,
  })

  const catalogoQ = useQuery({
    queryKey: ["inventario", "productos", "catalogo", { busqueda, catTipo, catCategoria, catPage }],
    queryFn: async () =>
      (
        await api.get<Page<Producto>>(`${API_PREFIX}/inventario/productos`, {
          params: {
            search: busqueda || undefined,
            tipo: catTipo || undefined,
            categoria_id: catCategoria || undefined,
            is_active: true,
            page: catPage,
            page_size: CATALOGO_PAGE_SIZE,
          },
        })
      ).data,
    placeholderData: (prev) => prev,
  })

  const catalogo = catalogoQ.data?.items ?? []

  const sugerenciasQ = useQuery({
    queryKey: ["inventario", "productos", "pos", busqueda],
    queryFn: async () =>
      (
        await api.get<Page<Producto>>(`${API_PREFIX}/inventario/productos`, {
          params: { search: busqueda, is_active: true, page_size: 8 },
        })
      ).data,
    // Con menos de dos letras la lista sería ruido; el escáner además manda
    // Enter antes de que el debounce dispare, así que no interfiere.
    enabled: busqueda.length >= 2,
  })

  const sugerencias = busqueda.length >= 2 ? (sugerenciasQ.data?.items ?? []) : []
  const mostrarSugerencias = sugerenciasOpen && busqueda.length >= 2

  useEffect(() => {
    setActiva(-1)
  }, [busqueda])

  // Al editar, se precarga la cotización una sola vez.
  const cotizacion = useQuery({
    queryKey: ["ventas", editId],
    queryFn: async () => (await api.get<VentaDetail>(`${API_PREFIX}/ventas/${editId}`)).data,
    enabled: editando,
  })

  const [cargada, setCargada] = useState(false)
  useEffect(() => {
    const v = cotizacion.data
    if (!v || cargada) return
    setClienteId(v.cliente?.id ?? "")
    setDescuento(Number(v.descuento) > 0 ? String(Number(v.descuento)) : "")
    setNotas(v.notas ?? "")
    setLineas(
      v.items.map((it) => ({
        producto_id: it.producto?.id ?? null,
        sku: it.producto?.sku ?? null,
        descripcion: it.descripcion,
        cantidad: String(Number(it.cantidad)),
        precio_unitario: String(Number(it.precio_unitario)),
        descuento: String(Number(it.descuento)),
        stock:
          it.producto && it.producto.tipo !== "SERVICIO"
            ? Number(it.producto.stock_actual)
            : null,
      })),
    )
    setCargada(true)
  }, [cotizacion.data, cargada])

  // El foco vuelve al campo de escaneo tras cada acción: la pistola escribe
  // donde esté el cursor, y si se perdió el foco el código se pierde.
  useEffect(() => {
    if (!pagoOpen) scanRef.current?.focus()
  }, [pagoOpen, lineas.length])

  const agregarProducto = (p: Producto) => {
    setLineas((prev) => {
      const i = prev.findIndex((l) => l.producto_id === p.id)
      // Escanear dos veces el mismo producto suma cantidad en vez de repetir
      // la línea, que es lo que espera quien está en el mostrador.
      if (i >= 0) {
        return prev.map((l, j) =>
          j === i ? { ...l, cantidad: String(Number(l.cantidad) + 1) } : l,
        )
      }
      return [
        ...prev,
        {
          producto_id: p.id,
          sku: p.sku,
          descripcion: p.nombre,
          cantidad: "1",
          precio_unitario: String(Number(p.precio_venta)),
          descuento: "0",
          // `stock: null` es la señal de "no controlar existencias" que ya usan
          // las líneas libres; un servicio entra por la misma puerta.
          stock: p.tipo === "SERVICIO" ? null : Number(p.stock_actual),
        },
      ]
    })
  }

  const elegirSugerencia = (p: Producto) => {
    agregarProducto(p)
    setCodigo("")
    setBusqueda("")
    setActiva(-1)
    setSugerenciasOpen(false)
    setErrorScan(null)
    scanRef.current?.focus()
  }

  /** Alta desde la cuadrícula. A diferencia del desplegable, no limpia el
   *  buscador: quien filtró por "cadena" suele agregar dos o tres seguidas. */
  const agregarDesdeCatalogo = (p: Producto) => {
    agregarProducto(p)
    setErrorScan(null)
    setSugerenciasOpen(false)
  }

  const escanear = useMutation({
    mutationFn: async (valor: string) =>
      (
        await api.get<Producto>(`${API_PREFIX}/inventario/productos/buscar`, {
          params: { codigo: valor },
        })
      ).data,
    onSuccess: (p) => {
      agregarProducto(p)
      setCodigo("")
      setErrorScan(null)
    },
    onError: (e) => {
      setErrorScan(apiErrorMessage(e, "Producto no encontrado"))
      setCodigo("")
    },
  })

  const setLinea = (i: number, campo: keyof Linea, valor: string) =>
    setLineas((prev) => prev.map((l, j) => (j === i ? { ...l, [campo]: valor } : l)))

  const sumarCantidad = (i: number, delta: number) =>
    setLineas((prev) =>
      prev.map((l, j) =>
        // Nunca baja de 1: quitar la línea es el papel del botón de basura, y
        // un 0 en el carrito sólo confunde al cobrar.
        j === i ? { ...l, cantidad: String(Math.max(1, (Number(l.cantidad) || 0) + delta)) } : l,
      ),
    )

  const quitarLinea = (i: number) => setLineas((prev) => prev.filter((_, j) => j !== i))

  const importeLinea = (l: Linea) =>
    Math.max(
      0,
      (Number(l.cantidad) || 0) * (Number(l.precio_unitario) || 0) - (Number(l.descuento) || 0),
    )

  const subtotal = useMemo(
    () => lineas.reduce((acc, l) => acc + importeLinea(l), 0),
    [lineas],
  )
  const total = Math.max(0, subtotal - (Number(descuento) || 0))

  const excedidas = lineas.filter((l) => l.stock !== null && Number(l.cantidad) > l.stock)

  const payloadItems = () =>
    lineas.map((l) => ({
      producto_id: l.producto_id,
      descripcion: l.descripcion,
      cantidad: Number(l.cantidad) || 1,
      precio_unitario: Number(l.precio_unitario) || 0,
      descuento: Number(l.descuento) || 0,
    }))

  const cobrar = useMutation({
    mutationFn: async (pagos: LineaPago[]) => {
      const { data } = await api.post<VentaDetail>(`${API_PREFIX}/ventas`, {
        tipo: "VENTA",
        cliente_id: clienteId || null,
        descuento: Number(descuento) || 0,
        notas: notas.trim() || null,
        items: payloadItems(),
        pagos: pagos.map((p) => ({
          metodo: p.metodo,
          monto: Number(p.monto),
          referencia: p.referencia.trim() || null,
        })),
      })
      return data
    },
    onSuccess: (v) => {
      qc.invalidateQueries({ queryKey: ["ventas"] })
      qc.invalidateQueries({ queryKey: ["caja"] })
      qc.invalidateQueries({ queryKey: ["inventario"] })
      navigate(`/ventas/${v.id}`)
    },
  })

  const cotizar = useMutation({
    mutationFn: async () => {
      const cuerpo = {
        cliente_id: clienteId || null,
        descuento: Number(descuento) || 0,
        notas: notas.trim() || null,
        items: payloadItems(),
      }
      if (editando) {
        const { data } = await api.patch<VentaDetail>(
          `${API_PREFIX}/ventas/${editId}`,
          cuerpo,
        )
        return data
      }
      const { data } = await api.post<VentaDetail>(`${API_PREFIX}/ventas`, {
        tipo: "COTIZACION",
        ...cuerpo,
      })
      return data
    },
    onSuccess: (v) => {
      qc.invalidateQueries({ queryKey: ["ventas"] })
      navigate(`/ventas/${v.id}`)
    },
  })

  const chipCategoria = (valor: string) =>
    valor === catCategoria
      ? "shrink-0 rounded-full bg-primary px-3.5 py-1.5 text-xs font-medium text-white"
      : "shrink-0 rounded-full border border-border px-3.5 py-1.5 text-xs font-medium text-muted-foreground hover:bg-accent"

  return (
    // En pantalla ancha, alto fijo y scroll dentro de cada panel: el carrito y
    // el botón de cobrar quedan siempre a la vista. Por debajo de xl no hay
    // sitio para dos columnas, así que se apilan y desplaza la página entera.
    <div className="flex flex-col xl:h-[calc(100vh-6.5rem)]">
      <PageHeader
        title={editando ? "Editar cotización" : "Nueva venta"}
        description={
          editando
            ? "Ajusta las líneas y guarda; el cobro se hace al convertirla en venta."
            : "Toca un ítem del catálogo, escanea su código o búscalo por nombre."
        }
        actions={
          caja.data ? (
            <Badge tone="success">
              Caja {caja.data.numero} abierta · {soles(caja.data.efectivo_esperado)}
            </Badge>
          ) : (
            <Badge tone="warning">Caja cerrada — sólo pagos digitales</Badge>
          )
        }
      />

      <div className="grid gap-4 xl:min-h-0 xl:flex-1 xl:grid-cols-[1fr_23rem]">
        {/* ==================== Catálogo ==================== */}
        <div className="flex min-w-0 flex-col rounded-lg border border-border bg-card xl:min-h-0">
          <div className="shrink-0 border-b border-border p-3">
            <div className="flex gap-2">
              <div className="relative flex-1">
                <ScanLine className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-primary" />
                <input
                  ref={scanRef}
                  value={codigo}
                  onChange={(e) => {
                    setCodigo(e.target.value)
                    setSugerenciasOpen(true)
                  }}
                  onFocus={() => setSugerenciasOpen(true)}
                  // El clic sobre una sugerencia se resuelve en onMouseDown, así
                  // que al llegar el blur ya se agregó la línea.
                  onBlur={() => setSugerenciasOpen(false)}
                  onKeyDown={(e) => {
                    if (e.key === "ArrowDown" && sugerencias.length) {
                      e.preventDefault()
                      setSugerenciasOpen(true)
                      setActiva((i) => (i + 1) % sugerencias.length)
                      return
                    }
                    if (e.key === "ArrowUp" && sugerencias.length) {
                      e.preventDefault()
                      setActiva((i) => (i <= 0 ? sugerencias.length - 1 : i - 1))
                      return
                    }
                    if (e.key === "Escape") {
                      setSugerenciasOpen(false)
                      setActiva(-1)
                      return
                    }
                    if (e.key === "Enter" && codigo.trim()) {
                      e.preventDefault()
                      // Sin sugerencia marcada se conserva el camino del escáner:
                      // busca el código exacto y agrega sin pasar por la lista.
                      const elegida = activa >= 0 ? sugerencias[activa] : undefined
                      if (elegida) {
                        elegirSugerencia(elegida)
                      } else {
                        escanear.mutate(codigo.trim())
                      }
                    }
                  }}
                  placeholder="Escanea el código, o escribe el SKU o el nombre del producto"
                  role="combobox"
                  aria-expanded={mostrarSugerencias}
                  aria-controls="sugerencias-productos"
                  aria-autocomplete="list"
                  className="w-full rounded-md border border-border bg-background py-2.5 pl-11 pr-3 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />

                {mostrarSugerencias && (
                  <ul
                    id="sugerencias-productos"
                    role="listbox"
                    className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-md border border-border bg-card shadow-lg"
                  >
                    {sugerencias.map((p, i) => (
                      <li key={p.id} role="option" aria-selected={i === activa}>
                        <button
                          type="button"
                          onMouseDown={(e) => {
                            e.preventDefault()
                            elegirSugerencia(p)
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
                              {p.tipo === "SERVICIO" ? (
                                "servicio"
                              ) : (
                                <>
                                  stock{" "}
                                  <span
                                    className={
                                      Number(p.stock_actual) <= 0 ? "text-state-danger" : ""
                                    }
                                  >
                                    {cantidad(p.stock_actual)}
                                  </span>
                                </>
                              )}
                            </span>
                          </span>
                          <span className="tabular shrink-0 font-medium">
                            {soles(p.precio_venta)}
                          </span>
                        </button>
                      </li>
                    ))}
                    {sugerencias.length === 0 && (
                      <li className="px-3 py-3 text-sm text-muted-foreground">
                        {sugerenciasQ.isFetching
                          ? "Buscando…"
                          : `Ningún producto activo coincide con “${busqueda}”`}
                      </li>
                    )}
                  </ul>
                )}
              </div>

              <Select
                value={catTipo}
                onChange={(e) => setCatTipo(e.target.value as "" | TipoItem)}
                className="w-36"
                aria-label="Tipo de ítem"
              >
                <option value="">Todo</option>
                <option value="PRODUCTO">Productos</option>
                <option value="SERVICIO">Servicios</option>
              </Select>
            </div>

            {errorScan && <p className="mt-2 text-xs text-state-danger">{errorScan}</p>}

            {/* Categorías como fichas: en pantalla táctil se filtra de un toque
                y sin desplegar un menú. */}
            <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
              <button
                type="button"
                onClick={() => setCatCategoria("")}
                className={chipCategoria("")}
              >
                Todos
              </button>
              {(categoriasQ.data ?? []).map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setCatCategoria(c.id)}
                  className={chipCategoria(c.id)}
                >
                  {c.nombre}
                </button>
              ))}
            </div>
          </div>

          <div
            className={
              catalogoQ.isFetching
                ? "flex-1 overflow-y-auto p-3 opacity-60 transition-opacity xl:min-h-0"
                : "flex-1 overflow-y-auto p-3 transition-opacity xl:min-h-0"
            }
          >
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 2xl:grid-cols-5">
              {catalogo.map((p) => {
                const agotado = p.tipo !== "SERVICIO" && Number(p.stock_actual) <= 0
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => agregarDesdeCatalogo(p)}
                    className="flex flex-col overflow-hidden rounded-lg border border-border text-left transition-colors hover:border-primary hover:bg-accent/40"
                  >
                    <div className="relative flex aspect-square items-center justify-center bg-muted/40">
                      {p.foto_url ? (
                        <img
                          src={p.foto_url}
                          alt=""
                          loading="lazy"
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <ImageOff className="h-7 w-7 text-muted-foreground/50" />
                      )}
                      {/* El precio va sobre la foto: es el dato que se busca de
                          un vistazo al elegir. */}
                      <span className="tabular absolute bottom-1.5 left-1.5 rounded-full bg-primary px-2 py-0.5 text-xs font-semibold text-white shadow">
                        {soles(p.precio_venta)}
                      </span>
                      {p.tipo === "SERVICIO" ? (
                        <span className="absolute right-1.5 top-1.5">
                          <Badge tone="info">Servicio</Badge>
                        </span>
                      ) : (
                        agotado && (
                          <span className="absolute right-1.5 top-1.5">
                            <Badge tone="danger">Sin stock</Badge>
                          </span>
                        )
                      )}
                    </div>
                    <div className="flex flex-1 flex-col gap-0.5 p-2">
                      <span className="line-clamp-2 text-sm font-medium leading-tight">
                        {p.nombre}
                      </span>
                      <span className="tabular mt-auto pt-1 text-xs text-muted-foreground">
                        {p.sku}
                        {p.tipo !== "SERVICIO" && ` · ${cantidad(p.stock_actual)}`}
                      </span>
                    </div>
                  </button>
                )
              })}
            </div>

            {catalogo.length === 0 && (
              <p className="py-16 text-center text-sm text-muted-foreground">
                {catalogoQ.isLoading
                  ? "Cargando catálogo…"
                  : busqueda
                    ? `Ningún ítem coincide con “${busqueda}”.`
                    : "No hay ítems activos en el catálogo."}
              </p>
            )}
          </div>

          <Paginacion
            compacta
            page={catPage}
            pageSize={CATALOGO_PAGE_SIZE}
            total={catalogoQ.data?.total ?? 0}
            onChange={setCatPage}
            etiqueta="ítems"
          />
        </div>

        {/* ==================== Carrito ==================== */}
        <div
          ref={carritoRef}
          className="flex min-w-0 scroll-mt-4 flex-col rounded-lg border border-border bg-card xl:min-h-0"
        >
          <div className="shrink-0 border-b border-border p-3">
            {/* Buscar por documento es la vía rápida del mostrador; el
                selector queda como respaldo para buscar por nombre. */}
            <BuscarClienteDocumento
              clienteId={clienteId}
              onSeleccionar={(c) => setClienteId(c?.id ?? "")}
            />
            {!clienteId && (
              <Select
                value={clienteId}
                onChange={(e) => setClienteId(e.target.value)}
                className="mt-2 py-1.5"
                aria-label="Cliente"
              >
                <option value="">Sin cliente (venta de mostrador)</option>
                {(clientes.data?.items ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.nombre} · {c.numero_documento}
                  </option>
                ))}
              </Select>
            )}
          </div>

          <div className="flex-1 overflow-y-auto xl:min-h-0">
            {lineas.length === 0 ? (
              <div className="flex h-full min-h-48 flex-col items-center justify-center gap-3 px-6 text-center">
                <span className="rounded-full bg-muted/60 p-5 text-muted-foreground">
                  <ShoppingCart className="h-8 w-8" />
                </span>
                <p className="text-sm text-muted-foreground">
                  Carrito vacío.
                  <br />
                  Toca un ítem del catálogo para agregarlo.
                </p>
              </div>
            ) : (
              lineas.map((l, i) => {
                const excede = l.stock !== null && Number(l.cantidad) > l.stock
                return (
                  <div key={i} className="border-b border-border p-2.5">
                    <div className="flex items-start gap-2">
                      <div className="min-w-0 flex-1">
                        <Input
                          value={l.descripcion}
                          onChange={(e) => setLinea(i, "descripcion", e.target.value)}
                          className="h-8 text-sm"
                        />
                        <p className="tabular mt-0.5 text-xs text-muted-foreground">
                          {l.sku ?? "Sin SKU"}
                          {l.stock !== null && (
                            <span className={excede ? "ml-2 text-state-danger" : "ml-2"}>
                              · stock {l.stock}
                            </span>
                          )}
                        </p>
                      </div>
                      <button
                        onClick={() => quitarLinea(i)}
                        className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-state-danger"
                        aria-label={`Quitar ${l.descripcion || "la línea"} del carrito`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>

                    <div className="mt-2 flex items-center gap-2">
                      <div className="flex items-center rounded-md border border-border">
                        <button
                          onClick={() => sumarCantidad(i, -1)}
                          className="px-2 py-1.5 text-muted-foreground hover:text-foreground"
                          aria-label="Quitar una unidad"
                        >
                          <Minus className="h-3.5 w-3.5" />
                        </button>
                        <input
                          value={l.cantidad}
                          onChange={(e) => setLinea(i, "cantidad", e.target.value)}
                          inputMode="decimal"
                          aria-label="Cantidad"
                          className={`tabular w-11 border-x border-border bg-transparent py-1.5 text-center text-sm focus:outline-none ${
                            excede ? "text-state-danger" : ""
                          }`}
                        />
                        <button
                          onClick={() => sumarCantidad(i, 1)}
                          className="px-2 py-1.5 text-muted-foreground hover:text-foreground"
                          aria-label="Agregar una unidad"
                        >
                          <Plus className="h-3.5 w-3.5" />
                        </button>
                      </div>

                      <Input
                        type="number"
                        min="0"
                        step="0.01"
                        value={l.precio_unitario}
                        onChange={(e) => setLinea(i, "precio_unitario", e.target.value)}
                        className="h-8 w-20 text-sm"
                        aria-label="Precio unitario"
                        title="Precio unitario"
                      />
                      <Input
                        type="number"
                        min="0"
                        step="0.01"
                        value={l.descuento}
                        onChange={(e) => setLinea(i, "descuento", e.target.value)}
                        className="h-8 w-16 text-sm"
                        aria-label="Descuento de la línea"
                        title="Descuento de la línea"
                      />
                      <span className="tabular ml-auto text-sm font-semibold">
                        {soles(importeLinea(l))}
                      </span>
                    </div>
                  </div>
                )
              })
            )}

            <button
              type="button"
              onClick={() =>
                setLineas((p) => [
                  ...p,
                  {
                    producto_id: null,
                    sku: null,
                    descripcion: "",
                    cantidad: "1",
                    precio_unitario: "",
                    descuento: "0",
                    stock: null,
                  },
                ])
              }
              className="flex w-full items-center justify-center gap-1.5 px-3 py-2.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <Plus className="h-3.5 w-3.5" />
              Línea libre (servicio o pieza sin SKU)
            </button>
          </div>

          <div className="shrink-0 border-t border-border p-3">
            <details className="mb-2">
              <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
                Descuento global y notas
              </summary>
              <div className="mt-2 space-y-2">
                <Field label="Descuento global (S/)">
                  <Input
                    type="number"
                    min="0"
                    step="0.01"
                    value={descuento}
                    onChange={(e) => setDescuento(e.target.value)}
                    placeholder="0.00"
                    className="h-8"
                  />
                </Field>
                <Field label="Notas">
                  <Textarea rows={2} value={notas} onChange={(e) => setNotas(e.target.value)} />
                </Field>
              </div>
            </details>

            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">
                Subtotal
                {lineas.length > 0 && (
                  <span className="tabular"> · {lineas.length} ítem(s)</span>
                )}
              </span>
              <span className="tabular">{soles(subtotal)}</span>
            </div>
            {Number(descuento) > 0 && (
              <div className="mt-1 flex justify-between text-sm">
                <span className="text-muted-foreground">Descuento</span>
                <span className="tabular text-state-danger">−{soles(descuento)}</span>
              </div>
            )}
            <div className="mt-2 flex items-baseline justify-between border-t border-border pt-2">
              <span className="font-semibold">Total</span>
              <span className="tabular text-2xl font-bold">{soles(total)}</span>
            </div>

            {excedidas.length > 0 && (
              <div className="mt-2 flex items-start gap-2 rounded-md border border-state-danger/30 bg-state-danger/10 px-3 py-2 text-xs text-state-danger">
                <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" />
                <span>
                  {excedidas.length === 1
                    ? "Una línea supera el stock disponible."
                    : `${excedidas.length} líneas superan el stock disponible.`}
                </span>
              </div>
            )}

            <FormError
              message={cotizar.isError ? apiErrorMessage(cotizar.error, "No se pudo cotizar") : null}
            />

            {!editando && (
              <Button
                className="mt-3 w-full py-3 text-base"
                disabled={lineas.length === 0 || total <= 0 || excedidas.length > 0}
                onClick={() => setPagoOpen(true)}
              >
                <Wallet className="h-4 w-4" />
                Cobrar {soles(total)}
              </Button>
            )}

            <Button
              variant={editando ? "primary" : "secondary"}
              className={editando ? "mt-3 w-full py-3 text-base" : "mt-2 w-full"}
              disabled={lineas.length === 0 || cotizar.isPending}
              onClick={() => cotizar.mutate()}
            >
              {cotizar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <FileText className="h-4 w-4" />
              )}
              {editando ? "Guardar cambios" : "Guardar como cotización"}
            </Button>
          </div>
        </div>
      </div>

      {/* En móvil los paneles se apilan y el carrito queda al final de un
          catálogo largo; esta barra mantiene el total a la vista y lleva a él
          de un toque. En escritorio el carrito ya está siempre visible. */}
      {lineas.length > 0 && (
        <div className="sticky bottom-0 z-20 -mx-4 mt-3 flex items-center justify-between gap-3 border-t border-border bg-card px-4 py-2.5 sm:-mx-6 sm:px-6 xl:hidden">
          <div>
            <p className="text-xs text-muted-foreground">
              <span className="tabular">{lineas.length}</span> ítem(s) en el carrito
            </p>
            <p className="tabular text-lg font-bold leading-tight">{soles(total)}</p>
          </div>
          <Button
            variant="secondary"
            onClick={() => carritoRef.current?.scrollIntoView({ behavior: "smooth" })}
          >
            <ShoppingCart className="h-4 w-4" />
            Ver carrito
          </Button>
        </div>
      )}

      <PagoModal
        open={pagoOpen}
        onClose={() => setPagoOpen(false)}
        total={total}
        cargando={cobrar.isPending}
        error={cobrar.isError ? cobrar.error : null}
        cajaAbierta={Boolean(caja.data)}
        onConfirmar={(pagos) => cobrar.mutate(pagos)}
      />
    </div>
  )
}
