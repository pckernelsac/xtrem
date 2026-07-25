import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams } from "react-router-dom"
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  Loader2,
  Package,
  Plus,
  Search,
  Trash2,
  UserPlus,
  X,
} from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { Button, Field, FormError, Input, Select, Textarea } from "@/components/ui/Form"
import { PageHeader } from "@/components/ui/PageHeader"
import { SkeletonCard } from "@/components/ui/skeleton"
import { BicicletaFormModal } from "@/features/clientes/BicicletaFormModal"
import { BuscarClienteDocumento } from "@/features/clientes/BuscarClienteDocumento"
import { ClienteFormModal } from "@/features/clientes/ClienteFormModal"
import type { Bicicleta, Cliente, Page } from "@/features/clientes/types"
import { BuscarProducto } from "@/features/inventario/BuscarProducto"
import { cantidad as fmtCantidad, type Producto as ProductoInv } from "@/features/inventario/types"
import {
  ETIQUETAS_RETIRADAS,
  SERVICIOS_COL1,
  SERVICIOS_COL2,
  soles,
  type FichaDetail,
  type ServicioGuardado,
  type ServicioRetirado,
} from "@/features/fichas/types"
import { METODOS, type MetodoPago } from "@/features/ventas/types"

/** Lo mínimo para mostrar la línea enlazada sin volver a consultar el catálogo. */
type ProductoLinea = {
  id: string
  sku: string
  nombre: string
  /** `null` en un servicio: no lleva existencias y nunca queda en rojo. */
  stock: number | null
}

type FilaRepuesto = {
  cantidad: string
  descripcion: string
  marca: string
  precio_unitario: string
  /** Null = repuesto de texto libre, que no mueve el inventario. */
  producto: ProductoLinea | null
}

const FILA_VACIA: FilaRepuesto = {
  cantidad: "1",
  descripcion: "",
  marca: "",
  precio_unitario: "",
  producto: null,
}

const aProductoLinea = (p: ProductoInv): ProductoLinea => ({
  id: p.id,
  sku: p.sku,
  nombre: p.nombre,
  stock: p.tipo === "SERVICIO" ? null : Number(p.stock_actual),
})

/** Datos mínimos para mostrar el cliente elegido; los cubren por igual la
 *  búsqueda por documento, la búsqueda por nombre y el alta desde la ficha. */
type ClienteSel = {
  id: string
  nombre: string
  tipo_documento: string
  numero_documento: string
}

function Seccion({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-border bg-card p-5">
      <h2 className="mb-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {titulo}
      </h2>
      {children}
    </section>
  )
}

export default function FichaFormPage() {
  const { id } = useParams()
  const editando = Boolean(id)
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [clienteId, setClienteId] = useState("")
  const [clienteSel, setClienteSel] = useState<ClienteSel | null>(null)
  const [clienteBusqueda, setClienteBusqueda] = useState("")
  const [clienteBusquedaDeb, setClienteBusquedaDeb] = useState("")
  const [clienteSugOpen, setClienteSugOpen] = useState(false)
  const [clienteModalOpen, setClienteModalOpen] = useState(false)
  const [bicicletaId, setBicicletaId] = useState("")
  const [biciModalOpen, setBiciModalOpen] = useState(false)
  const [canal, setCanal] = useState("")
  const [servicios, setServicios] = useState<Set<ServicioGuardado>>(new Set())
  const [servicioOtro, setServicioOtro] = useState("")
  const [diagnostico, setDiagnostico] = useState("")
  const [trabajo, setTrabajo] = useState("")
  const [tiempo, setTiempo] = useState("")
  const [observaciones, setObservaciones] = useState("")
  const [garantia, setGarantia] = useState("")
  const [costoServicio, setCostoServicio] = useState("")
  const [adelanto, setAdelanto] = useState("")
  const [adelantoMetodo, setAdelantoMetodo] = useState<MetodoPago>("EFECTIVO")
  const [filas, setFilas] = useState<FilaRepuesto[]>([{ ...FILA_VACIA }])

  const fichaQ = useQuery({
    queryKey: ["fichas", id],
    queryFn: async () => (await api.get<FichaDetail>(`${API_PREFIX}/fichas/${id}`)).data,
    enabled: editando,
  })

  // Buscador de cliente por nombre/documento: el desplegable plano no escala
  // cuando el directorio crece, así que se consulta al servidor con debounce.
  useEffect(() => {
    const t = setTimeout(() => setClienteBusquedaDeb(clienteBusqueda.trim()), 300)
    return () => clearTimeout(t)
  }, [clienteBusqueda])

  const clientesQ = useQuery({
    queryKey: ["clientes", "ficha-buscar", clienteBusquedaDeb],
    queryFn: async () =>
      (
        await api.get<Page<Cliente>>(`${API_PREFIX}/clientes`, {
          params: { search: clienteBusquedaDeb, is_active: true, page_size: 8 },
        })
      ).data,
    enabled: clienteBusquedaDeb.length >= 2,
  })

  const clientesSug = clienteBusquedaDeb.length >= 2 ? (clientesQ.data?.items ?? []) : []
  const mostrarClientesSug = clienteSugOpen && clienteBusquedaDeb.length >= 2

  const elegirCliente = (c: ClienteSel | null) => {
    setClienteSel(c)
    setClienteId(c?.id ?? "")
    // La bici depende del dueño: cambiar de cliente la invalida.
    setBicicletaId("")
    setClienteBusqueda("")
    setClienteSugOpen(false)
  }

  // Sólo las bicicletas del cliente elegido: el backend rechaza una ficha
  // cuya bici pertenezca a otra persona, así que no la ofrecemos siquiera.
  const bicisQ = useQuery({
    queryKey: ["bicicletas", "de-cliente", clienteId],
    queryFn: async () =>
      (
        await api.get<Page<Bicicleta>>(`${API_PREFIX}/bicicletas`, {
          params: { cliente_id: clienteId, is_active: true, page_size: 100 },
        })
      ).data,
    enabled: Boolean(clienteId),
  })

  useEffect(() => {
    const f = fichaQ.data
    if (!f) return
    setClienteId(f.cliente.id)
    setClienteSel(f.cliente)
    setBicicletaId(f.bicicleta?.id ?? "")
    setCanal(f.canal_referencia ?? "")
    setServicios(new Set(f.servicios))
    setServicioOtro(f.servicio_otro ?? "")
    setDiagnostico(f.diagnostico_inicial ?? "")
    setTrabajo(f.trabajo_realizado ?? "")
    setTiempo(f.tiempo_invertido_min?.toString() ?? "")
    setObservaciones(f.observaciones ?? "")
    setGarantia(f.garantia_dias?.toString() ?? "")
    setCostoServicio(Number(f.costo_servicio) ? String(Number(f.costo_servicio)) : "")
    setAdelanto(Number(f.adelanto) ? String(Number(f.adelanto)) : "")
    setFilas(
      f.repuestos.length
        ? f.repuestos.map((r) => ({
            cantidad: String(Number(r.cantidad)),
            descripcion: r.descripcion,
            marca: r.marca ?? "",
            precio_unitario: String(Number(r.precio_unitario)),
            producto: r.producto
              ? {
                  id: r.producto.id,
                  sku: r.producto.sku,
                  nombre: r.producto.nombre,
                  stock:
                    r.producto.tipo === "SERVICIO" ? null : Number(r.producto.stock_actual),
                }
              : null,
          }))
        : [{ ...FILA_VACIA }],
    )
  }, [fichaQ.data])

  const totalRepuestos = useMemo(
    () =>
      filas.reduce(
        (acc, f) => acc + (Number(f.cantidad) || 0) * (Number(f.precio_unitario) || 0),
        0,
      ),
    [filas],
  )
  const manoObra = Number(costoServicio) || 0
  const total = totalRepuestos + manoObra
  const saldo = total - (Number(adelanto) || 0)

  const retirados = [...servicios].filter(
    (s): s is ServicioRetirado => s in ETIQUETAS_RETIRADAS,
  )

  const toggleServicio = (code: ServicioGuardado) => {
    setServicios((prev) => {
      const next = new Set(prev)
      next.has(code) ? next.delete(code) : next.add(code)
      return next
    })
  }

  const setFila = (i: number, campo: keyof FilaRepuesto, valor: string) =>
    setFilas((prev) => prev.map((f, j) => (j === i ? { ...f, [campo]: valor } : f)))

  /** Unidades que esta ficha puede consumir de un producto. Al editar, lo ya
   *  consumido por ella sigue reservado para ella y vuelve a estar disponible. */
  const disponibleDe = (productoId: string, stock: number | null): number | null => {
    if (stock === null) return null
    const yaEnFicha = (fichaQ.data?.repuestos ?? [])
      .filter((r) => r.producto?.id === productoId)
      .reduce((acc, r) => acc + Number(r.cantidad), 0)
    return stock + yaEnFicha
  }

  const stockDisponible = (fila: FilaRepuesto): number | null =>
    fila.producto ? disponibleDe(fila.producto.id, fila.producto.stock) : null

  /** Lo que el buscador debe ofrecer: lo disponible menos lo que ya se llevaron
   *  las líneas del formulario, para no prometer piezas dos veces. */
  const disponibleParaBuscador = (p: ProductoInv): number | null => {
    const disponible = disponibleDe(p.id, p.tipo === "SERVICIO" ? null : Number(p.stock_actual))
    if (disponible === null) return null
    const comprometido = filas
      .filter((f) => f.producto?.id === p.id)
      .reduce((acc, f) => acc + (Number(f.cantidad) || 0), 0)
    return disponible - comprometido
  }

  /** Alta desde el buscador: rellena la línea con los datos del catálogo. */
  const agregarProducto = (p: ProductoInv) => {
    setFilas((prev) => {
      // Repetir el mismo producto suma cantidad en vez de duplicar la línea:
      // el stock las ve como una sola y dos líneas iguales sólo confunden.
      const i = prev.findIndex((f) => f.producto?.id === p.id)
      if (i >= 0) {
        return prev.map((f, j) =>
          j === i ? { ...f, cantidad: String((Number(f.cantidad) || 0) + 1) } : f,
        )
      }

      const fila: FilaRepuesto = {
        cantidad: "1",
        descripcion: p.nombre,
        marca: p.marca ?? "",
        precio_unitario: String(Number(p.precio_venta)),
        producto: aProductoLinea(p),
      }

      // La fila en blanco inicial es andamiaje: se aprovecha antes de crear otra.
      const vacia = prev.findIndex((f) => !f.producto && !f.descripcion.trim())
      if (vacia >= 0) return prev.map((f, j) => (j === vacia ? fila : f))
      return [...prev, fila]
    })
  }

  /** Desenlazar deja la línea como texto libre: se conserva lo escrito, pero
   *  deja de mover el almacén. */
  const desenlazar = (i: number) =>
    setFilas((prev) => prev.map((f, j) => (j === i ? { ...f, producto: null } : f)))

  const excedidas = filas.filter((f) => {
    const disponible = stockDisponible(f)
    return disponible !== null && Number(f.cantidad) > disponible
  })

  const guardar = useMutation({
    mutationFn: async () => {
      const payload = {
        canal_referencia: canal.trim() || null,
        servicios: [...servicios],
        servicio_otro: servicioOtro.trim() || null,
        costo_servicio: Number(costoServicio) || 0,
        diagnostico_inicial: diagnostico.trim() || null,
        trabajo_realizado: trabajo.trim() || null,
        tiempo_invertido_min: tiempo ? Number(tiempo) : null,
        observaciones: observaciones.trim() || null,
        garantia_dias: garantia ? Number(garantia) : null,
        // Las filas en blanco son andamiaje de la UI, no repuestos reales.
        repuestos: filas
          .filter((f) => f.descripcion.trim())
          .map((f) => ({
            cantidad: Number(f.cantidad) || 1,
            descripcion: f.descripcion.trim(),
            marca: f.marca.trim() || null,
            precio_unitario: Number(f.precio_unitario) || 0,
            producto_id: f.producto?.id ?? null,
          })),
      }

      if (editando) {
        await api.patch(`${API_PREFIX}/fichas/${id}`, payload)
        return id!
      }
      const { data } = await api.post<FichaDetail>(`${API_PREFIX}/fichas`, {
        ...payload,
        cliente_id: clienteId,
        bicicleta_id: bicicletaId || null,
        adelanto: Number(adelanto) || 0,
        adelanto_metodo: Number(adelanto) > 0 ? adelantoMetodo : null,
      })
      return data.id
    },
    onSuccess: (fichaId) => {
      qc.invalidateQueries({ queryKey: ["fichas"] })
      qc.invalidateQueries({ queryKey: ["bicicletas"] })
      navigate(`/fichas/${fichaId}`, { replace: true })
    },
  })

  if (editando && fichaQ.isLoading) {
    return (
      <div className="space-y-4">
        <SkeletonCard />
        <SkeletonCard className="h-56" />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl">
      <button
        onClick={() => navigate(-1)}
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Volver
      </button>

      <PageHeader
        title={editando ? `Editar servicio N° ${fichaQ.data?.numero}` : "Nuevo servicio"}
        description="Los campos coinciden con la ficha impresa del taller."
      />

      <form
        onSubmit={(e) => {
          e.preventDefault()
          guardar.mutate()
        }}
        className="space-y-4"
      >
        <Seccion titulo="Cliente y bicicleta">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Cliente" required>
              {editando ? (
                // El cliente no se cambia después de crear la ficha.
                <Input
                  value={
                    clienteSel
                      ? `${clienteSel.nombre} · ${clienteSel.tipo_documento} ${clienteSel.numero_documento}`
                      : ""
                  }
                  disabled
                  readOnly
                />
              ) : clienteSel ? (
                // Cliente elegido (por cualquier vía): "chip" con opción de quitarlo.
                <div className="rounded-lg border border-state-success/30 bg-state-success/5 px-3 py-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="flex items-center gap-1.5 text-sm font-medium">
                        <Check className="h-3.5 w-3.5 shrink-0 text-state-success" />
                        <span className="truncate">{clienteSel.nombre}</span>
                      </p>
                      <p className="tabular mt-0.5 text-xs text-muted-foreground">
                        {clienteSel.tipo_documento} {clienteSel.numero_documento}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => elegirCliente(null)}
                      className="shrink-0 rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
                      aria-label="Quitar cliente"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  {/* Buscar por documento es la vía rápida (consulta RENIEC/SUNAT);
                      debajo, la búsqueda por nombre y el alta al vuelo. */}
                  <BuscarClienteDocumento clienteId={clienteId} onSeleccionar={elegirCliente} />

                  <div className="relative">
                    <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <input
                      value={clienteBusqueda}
                      onChange={(e) => {
                        setClienteBusqueda(e.target.value)
                        setClienteSugOpen(true)
                      }}
                      onFocus={() => setClienteSugOpen(true)}
                      onBlur={() => setClienteSugOpen(false)}
                      placeholder="Buscar cliente por nombre o documento"
                      role="combobox"
                      aria-expanded={mostrarClientesSug}
                      aria-controls="sugerencias-clientes-ficha"
                      aria-autocomplete="list"
                      className="w-full rounded-md border border-border bg-background py-2 pl-8 pr-3 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                    />

                    {mostrarClientesSug && (
                      <ul
                        id="sugerencias-clientes-ficha"
                        role="listbox"
                        className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-md border border-border bg-card shadow-lg"
                      >
                        {clientesSug.map((c) => (
                          <li key={c.id} role="option" aria-selected={false}>
                            <button
                              type="button"
                              onMouseDown={(e) => {
                                e.preventDefault()
                                elegirCliente(c)
                              }}
                              className="flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left text-sm hover:bg-accent"
                            >
                              <span className="block max-w-full truncate font-medium">{c.nombre}</span>
                              <span className="tabular block max-w-full truncate text-xs text-muted-foreground">
                                {c.tipo_documento} {c.numero_documento}
                                {c.telefono ? ` · ${c.telefono}` : ""}
                              </span>
                            </button>
                          </li>
                        ))}
                        {clientesSug.length === 0 && (
                          <li className="px-3 py-3 text-sm text-muted-foreground">
                            {clientesQ.isFetching
                              ? "Buscando…"
                              : `Ningún cliente coincide con “${clienteBusquedaDeb}”`}
                          </li>
                        )}
                      </ul>
                    )}
                  </div>

                  <Button
                    type="button"
                    variant="secondary"
                    className="w-full"
                    onClick={() => setClienteModalOpen(true)}
                  >
                    <UserPlus className="h-4 w-4" />
                    Nuevo cliente
                  </Button>
                </div>
              )}
            </Field>

            <Field
              label="Bicicleta (opcional)"
              hint={
                clienteId && bicisQ.data?.items.length === 0
                  ? "Este cliente no tiene bicicletas registradas. Usa “Registrar nueva”."
                  : "Déjalo en blanco si el servicio no involucra una bicicleta."
              }
            >
              <div className="flex gap-2">
                <Select
                  value={bicicletaId}
                  disabled={editando || !clienteId}
                  onChange={(e) => setBicicletaId(e.target.value)}
                  className="flex-1"
                >
                  <option value="">
                    {clienteId ? "Sin bicicleta / no aplica" : "Elige primero el cliente"}
                  </option>
                  {(bicisQ.data?.items ?? []).map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.descripcion}
                      {b.numero_serie ? ` · ${b.numero_serie}` : ""}
                    </option>
                  ))}
                </Select>
                {!editando && (
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={!clienteId}
                    onClick={() => setBiciModalOpen(true)}
                    title={
                      clienteId
                        ? "Registrar la bicicleta que entra a revisión"
                        : "Elige primero el cliente"
                    }
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Registrar nueva
                  </Button>
                )}
              </div>
            </Field>
          </div>

          {editando && (
            <p className="mt-3 text-xs text-muted-foreground">
              El cliente y la bicicleta no se cambian después de crear la ficha: el N° de ficha ya
              quedó asociado a ellos.
            </p>
          )}

          <Field label="¿Cómo nos conoció?" className="mt-4">
            <Input
              value={canal}
              onChange={(e) => setCanal(e.target.value)}
              placeholder="Recomendación, redes sociales, pasaba por la tienda..."
            />
          </Field>
        </Seccion>

        <Seccion titulo="Servicio solicitado">
          <div className="grid gap-2 sm:grid-cols-2">
            {[...SERVICIOS_COL1, ...SERVICIOS_COL2].map((s) => (
              <label
                key={s.value}
                className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm hover:bg-accent"
              >
                <input
                  type="checkbox"
                  checked={servicios.has(s.value)}
                  onChange={() => toggleServicio(s.value)}
                  className="h-3.5 w-3.5 accent-[var(--primary)]"
                />
                {s.label}
              </label>
            ))}
          </div>

          {/* Una ficha anterior al cambio de checklist puede traer servicios
              que ya no se ofrecen. Se muestran igual: dejarlos invisibles pero
              guardados sería mentir sobre lo que se pidió. */}
          {retirados.length > 0 && (
            <div className="mt-3 rounded-md border border-border bg-muted/30 p-3">
              <p className="mb-2 text-xs text-muted-foreground">
                Servicios de la lista anterior, marcados cuando se creó este servicio. Al
                desmarcarlos ya no podrán volver a elegirse.
              </p>
              <div className="grid gap-2 sm:grid-cols-2">
                {retirados.map((code) => (
                  <label
                    key={code}
                    className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm hover:bg-accent"
                  >
                    <input
                      type="checkbox"
                      checked
                      onChange={() => toggleServicio(code)}
                      className="h-3.5 w-3.5 accent-[var(--primary)]"
                    />
                    {ETIQUETAS_RETIRADAS[code]}
                  </label>
                ))}
              </div>
            </div>
          )}

          <Field label="Otro servicio" className="mt-3">
            <Input
              value={servicioOtro}
              onChange={(e) => setServicioOtro(e.target.value)}
              placeholder="Describe el servicio que no está en la lista"
            />
          </Field>

          <Field label="Diagnóstico inicial" className="mt-4">
            <Textarea
              rows={3}
              value={diagnostico}
              onChange={(e) => setDiagnostico(e.target.value)}
              placeholder="Estado en que llega la bicicleta, fallas detectadas..."
            />
          </Field>
        </Seccion>

        <Seccion titulo="Repuestos / componentes utilizados">
          <p className="mb-3 text-xs text-muted-foreground">
            Busca la pieza en el inventario y agrégala: se descuenta del stock en cuanto guardas
            el servicio. Las líneas sin enlazar son sólo texto y no mueven el almacén.
          </p>

          {/* El buscador vive fuera de la tabla a propósito: dentro, el scroll
              horizontal recortaría el desplegable de sugerencias. */}
          <div className="mb-3">
            <BuscarProducto
              onSeleccionar={agregarProducto}
              disponibleDe={disponibleParaBuscador}
              placeholder="Buscar producto del inventario por SKU, nombre o marca"
            />
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <th className="w-56 pb-2">Producto del inventario</th>
                  <th className="w-20 pb-2">Cant.</th>
                  <th className="pb-2">Descripción</th>
                  <th className="w-28 pb-2">Marca</th>
                  <th className="w-24 pb-2">Precio</th>
                  <th className="w-24 pb-2 text-right">Subtotal</th>
                  <th className="w-10 pb-2" />
                </tr>
              </thead>
              <tbody>
                {filas.map((f, i) => {
                  const disponible = stockDisponible(f)
                  const excede = disponible !== null && Number(f.cantidad) > disponible
                  return (
                    <tr key={i}>
                      <td className="py-1 pr-2 align-top">
                        {f.producto ? (
                          <div
                            className={
                              excede
                                ? "rounded-md border border-state-danger/40 bg-state-danger/5 px-2.5 py-1.5"
                                : "rounded-md border border-state-success/30 bg-state-success/5 px-2.5 py-1.5"
                            }
                          >
                            <div className="flex items-start justify-between gap-1.5">
                              <div className="min-w-0">
                                <p className="tabular flex items-center gap-1 text-xs font-medium">
                                  <Package className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                                  <span className="truncate">{f.producto.sku}</span>
                                </p>
                                <p
                                  className={
                                    excede
                                      ? "mt-0.5 text-[11px] text-state-danger"
                                      : "mt-0.5 text-[11px] text-muted-foreground"
                                  }
                                >
                                  {disponible === null
                                    ? "Servicio · sin stock"
                                    : excede
                                      ? `Sólo hay ${fmtCantidad(disponible)} disponibles`
                                      : `Disponible: ${fmtCantidad(disponible)}`}
                                </p>
                              </div>
                              <button
                                type="button"
                                onClick={() => desenlazar(i)}
                                className="shrink-0 rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                                title="Desenlazar del inventario (la línea pasa a texto libre)"
                                aria-label="Desenlazar del inventario"
                              >
                                <X className="h-3 w-3" />
                              </button>
                            </div>
                          </div>
                        ) : (
                          <p className="px-1 py-2 text-xs text-muted-foreground">
                            Texto libre · no mueve el almacén
                          </p>
                        )}
                      </td>
                      <td className="py-1 pr-2 align-top">
                        <Input
                          type="number"
                          min="0"
                          step="0.01"
                          value={f.cantidad}
                          onChange={(e) => setFila(i, "cantidad", e.target.value)}
                          className={excede ? "border-state-danger" : undefined}
                        />
                      </td>
                      <td className="py-1 pr-2 align-top">
                        <Input
                          value={f.descripcion}
                          onChange={(e) => setFila(i, "descripcion", e.target.value)}
                          placeholder="Cadena 12v XT M8100"
                        />
                      </td>
                      <td className="py-1 pr-2 align-top">
                        <Input
                          value={f.marca}
                          onChange={(e) => setFila(i, "marca", e.target.value)}
                          placeholder="Shimano"
                        />
                      </td>
                      <td className="py-1 pr-2 align-top">
                        <Input
                          type="number"
                          min="0"
                          step="0.01"
                          value={f.precio_unitario}
                          onChange={(e) => setFila(i, "precio_unitario", e.target.value)}
                          placeholder="0.00"
                        />
                      </td>
                      <td className="tabular py-1 pr-2 pt-3 text-right align-top text-muted-foreground">
                        {soles((Number(f.cantidad) || 0) * (Number(f.precio_unitario) || 0))}
                      </td>
                      <td className="py-1 pt-2 align-top">
                        <button
                          type="button"
                          onClick={() => setFilas((p) => p.filter((_, j) => j !== i))}
                          disabled={filas.length === 1}
                          className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-state-danger disabled:opacity-30"
                          aria-label="Quitar fila"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div className="mt-3 flex items-center justify-between">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setFilas((p) => [...p, { ...FILA_VACIA }])}
            >
              <Plus className="h-3.5 w-3.5" />
              Línea libre (pieza sin SKU)
            </Button>
            <div className="text-sm">
              <span className="text-muted-foreground">Subtotal repuestos</span>{" "}
              <span className="tabular text-lg font-semibold">{soles(totalRepuestos)}</span>
            </div>
          </div>

          {/* El backend rechaza la ficha entera con un 409 si falta stock; se
              avisa antes para no perder lo escrito en un guardado fallido. */}
          {excedidas.length > 0 && (
            <div className="mt-3 flex items-start gap-2 rounded-md border border-state-danger/30 bg-state-danger/10 px-3 py-2 text-xs text-state-danger">
              <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" />
              <span>
                {excedidas.length === 1
                  ? "Una línea supera el stock disponible: ajusta la cantidad o desenlázala del inventario."
                  : `${excedidas.length} líneas superan el stock disponible: ajusta las cantidades o desenlázalas del inventario.`}
              </span>
            </div>
          )}
        </Seccion>

        <Seccion titulo="Cobro">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Costo del servicio solicitado"
              hint="Aparte de los repuestos. Puede ser el único cobro de un servicio sin piezas."
            >
              <Input
                type="number"
                min="0"
                step="0.01"
                value={costoServicio}
                onChange={(e) => setCostoServicio(e.target.value)}
                placeholder="0.00"
              />
            </Field>

            {!editando ? (
              <Field label="Adelanto cobrado al recibir" hint="Entra a caja al crear el servicio.">
                <div className="flex gap-2">
                  <Input
                    type="number"
                    min="0"
                    step="0.01"
                    value={adelanto}
                    onChange={(e) => setAdelanto(e.target.value)}
                    placeholder="0.00"
                    className="flex-1"
                  />
                  <Select
                    value={adelantoMetodo}
                    onChange={(e) => setAdelantoMetodo(e.target.value as MetodoPago)}
                    disabled={!(Number(adelanto) > 0)}
                    className="w-36"
                  >
                    {METODOS.map((m) => (
                      <option key={m.value} value={m.value}>
                        {m.label}
                      </option>
                    ))}
                  </Select>
                </div>
              </Field>
            ) : (
              <Field label="Adelanto cobrado al recibir">
                <Input value={soles(adelanto || 0)} disabled readOnly />
              </Field>
            )}
          </div>

          <div className="mt-4 flex flex-wrap justify-end gap-x-8 gap-y-2 border-t border-border pt-4 text-sm">
            <div>
              <span className="text-muted-foreground">Total del servicio</span>{" "}
              <span className="tabular text-lg font-semibold">{soles(total)}</span>
            </div>
            {Number(adelanto) > 0 && (
              <div>
                <span className="text-muted-foreground">Saldo restante</span>{" "}
                <span className="tabular text-lg font-semibold">{soles(saldo)}</span>
              </div>
            )}
          </div>
        </Seccion>

        <Seccion titulo="Trabajo realizado y observaciones">
          <Field label="Trabajo realizado">
            <Textarea
              rows={3}
              value={trabajo}
              onChange={(e) => setTrabajo(e.target.value)}
              placeholder="Describe lo que se hizo en el taller..."
            />
          </Field>

          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Field label="Tiempo invertido (minutos)">
              <Input
                type="number"
                min="0"
                value={tiempo}
                onChange={(e) => setTiempo(e.target.value)}
                placeholder="195"
              />
            </Field>
            <Field label="Garantía (días)">
              <Input
                type="number"
                min="0"
                value={garantia}
                onChange={(e) => setGarantia(e.target.value)}
                placeholder="30"
              />
            </Field>
          </div>

          <Field label="Observaciones" className="mt-4">
            <Textarea
              rows={3}
              value={observaciones}
              onChange={(e) => setObservaciones(e.target.value)}
              placeholder="Notas internas, recomendaciones al cliente..."
            />
          </Field>
        </Seccion>

        <FormError
          message={
            guardar.isError ? apiErrorMessage(guardar.error, "No se pudo guardar el servicio") : null
          }
        />

        <div className="flex justify-end gap-2 pb-4">
          <Button type="button" variant="secondary" onClick={() => navigate(-1)}>
            Cancelar
          </Button>
          <Button
            type="submit"
            disabled={guardar.isPending || (!editando && !clienteId) || excedidas.length > 0}
          >
            {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {editando ? "Guardar cambios" : "Crear servicio"}
          </Button>
        </div>
      </form>

      {/* Registrar al vuelo la bicicleta que entra a revisión, sin salir del servicio. */}
      <BicicletaFormModal
        open={biciModalOpen}
        onClose={() => setBiciModalOpen(false)}
        clienteId={clienteId}
        onCreated={(b) => setBicicletaId(b.id)}
      />

      {/* Alta de cliente sin salir de la ficha: al crearlo queda seleccionado. */}
      <ClienteFormModal
        open={clienteModalOpen}
        onClose={() => setClienteModalOpen(false)}
        onCreated={elegirCliente}
      />
    </div>
  )
}
