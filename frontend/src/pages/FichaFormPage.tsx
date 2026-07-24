import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams } from "react-router-dom"
import { ArrowLeft, Loader2, Plus, Trash2 } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { Button, Field, FormError, Input, Select, Textarea } from "@/components/ui/Form"
import { PageHeader } from "@/components/ui/PageHeader"
import { SkeletonCard } from "@/components/ui/skeleton"
import { BicicletaFormModal } from "@/features/clientes/BicicletaFormModal"
import { BuscarClienteDocumento } from "@/features/clientes/BuscarClienteDocumento"
import type { Bicicleta, Cliente, Page } from "@/features/clientes/types"
import { cantidad as fmtCantidad, type Producto as ProductoInv } from "@/features/inventario/types"
import {
  SERVICIOS_COL1,
  SERVICIOS_COL2,
  soles,
  type FichaDetail,
  type ServicioCodigo,
} from "@/features/fichas/types"
import { METODOS, type MetodoPago } from "@/features/ventas/types"

type FilaRepuesto = {
  cantidad: string
  descripcion: string
  marca: string
  precio_unitario: string
  /** Vacío = repuesto de texto libre, que no mueve el inventario. */
  producto_id: string
}

const FILA_VACIA: FilaRepuesto = {
  cantidad: "1",
  descripcion: "",
  marca: "",
  precio_unitario: "",
  producto_id: "",
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
  const [bicicletaId, setBicicletaId] = useState("")
  const [biciModalOpen, setBiciModalOpen] = useState(false)
  const [canal, setCanal] = useState("")
  const [servicios, setServicios] = useState<Set<ServicioCodigo>>(new Set())
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

  const clientesQ = useQuery({
    queryKey: ["clientes", "activos-select"],
    queryFn: async () =>
      (
        await api.get<Page<Cliente>>(`${API_PREFIX}/clientes`, {
          params: { is_active: true, page_size: 200 },
        })
      ).data,
  })

  const productosQ = useQuery({
    queryKey: ["inventario", "productos", "select-ficha"],
    queryFn: async () =>
      (
        await api.get<Page<ProductoInv>>(`${API_PREFIX}/inventario/productos`, {
          params: { is_active: true, page_size: 300 },
        })
      ).data,
  })

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
            producto_id: r.producto?.id ?? "",
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

  const toggleServicio = (code: ServicioCodigo) => {
    setServicios((prev) => {
      const next = new Set(prev)
      next.has(code) ? next.delete(code) : next.add(code)
      return next
    })
  }

  const setFila = (i: number, campo: keyof FilaRepuesto, valor: string) =>
    setFilas((prev) => prev.map((f, j) => (j === i ? { ...f, [campo]: valor } : f)))

  /** Al elegir un producto del catálogo se rellena la línea con sus datos. */
  const elegirProducto = (i: number, productoId: string) => {
    const p = (productosQ.data?.items ?? []).find((x) => x.id === productoId)
    setFilas((prev) =>
      prev.map((f, j) =>
        j !== i
          ? f
          : p
            ? {
                ...f,
                producto_id: p.id,
                descripcion: p.nombre,
                marca: p.marca ?? "",
                precio_unitario: String(Number(p.precio_venta)),
              }
            : { ...f, producto_id: "" },
      ),
    )
  }

  const stockDisponible = (fila: FilaRepuesto): number | null => {
    if (!fila.producto_id) return null
    const p = (productosQ.data?.items ?? []).find((x) => x.id === fila.producto_id)
    if (!p) return null
    // Al editar, lo ya consumido por esta ficha sigue reservado para ella.
    const yaEnFicha = fichaQ.data?.repuestos
      .filter((r) => r.producto?.id === fila.producto_id)
      .reduce((acc, r) => acc + Number(r.cantidad), 0)
    return Number(p.stock_actual) + (yaEnFicha ?? 0)
  }

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
            producto_id: f.producto_id || null,
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
          {/* Al recibir el servicio, lo primero que se pide es el documento del
              dueño: se busca o se registra sin salir de la ficha. */}
          {!editando && (
            <Field
              label="Buscar cliente por documento"
              className="mb-4"
              hint="Si no está registrado, se consulta RENIEC/SUNAT y se crea al momento"
            >
              <BuscarClienteDocumento
                clienteId={clienteId}
                onSeleccionar={(c) => {
                  setClienteId(c?.id ?? "")
                  // La bici depende del dueño: cambiar de cliente la invalida.
                  setBicicletaId("")
                }}
              />
            </Field>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={editando ? "Cliente" : "…o elígelo de la lista"} required>
              <Select
                required
                value={clienteId}
                disabled={editando}
                onChange={(e) => {
                  setClienteId(e.target.value)
                  setBicicletaId("")
                }}
              >
                <option value="">Selecciona un cliente</option>
                {(clientesQ.data?.items ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.nombre} · {c.tipo_documento} {c.numero_documento}
                  </option>
                ))}
              </Select>
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
            Al enlazar una línea con un producto del inventario, la pieza se descuenta del stock
            en cuanto guardas la ficha. Las líneas sin enlazar son sólo texto y no mueven el
            almacén.
          </p>

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
                        <Select
                          value={f.producto_id}
                          onChange={(e) => elegirProducto(i, e.target.value)}
                          disabled={productosQ.isLoading}
                        >
                          <option value="">Sin enlazar (texto libre)</option>
                          {(productosQ.data?.items ?? []).map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.sku} · {p.nombre} ({fmtCantidad(p.stock_actual)})
                            </option>
                          ))}
                        </Select>
                        {disponible !== null && (
                          <p
                            className={
                              excede
                                ? "mt-1 text-[11px] text-state-danger"
                                : "mt-1 text-[11px] text-muted-foreground"
                            }
                          >
                            {excede
                              ? `Sólo hay ${fmtCantidad(disponible)} disponibles`
                              : `Disponible: ${fmtCantidad(disponible)}`}
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
              Agregar fila
            </Button>
            <div className="text-sm">
              <span className="text-muted-foreground">Subtotal repuestos</span>{" "}
              <span className="tabular text-lg font-semibold">{soles(totalRepuestos)}</span>
            </div>
          </div>
        </Seccion>

        <Seccion titulo="Cobro">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Costo de servicio / mano de obra"
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
          <Button type="submit" disabled={guardar.isPending}>
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
    </div>
  )
}
