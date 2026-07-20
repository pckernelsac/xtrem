import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ArrowDownRight,
  ArrowUpRight,
  ChevronRight,
  Lock,
  LockOpen,
  Loader2,
  Plus,
  Wallet,
} from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { usePermission } from "@/lib/auth"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/Badge"
import { Button, Field, FormError, Input, Select, Textarea } from "@/components/ui/Form"
import { Modal } from "@/components/ui/Modal"
import { PageHeader } from "@/components/ui/PageHeader"
import { Paginacion } from "@/components/ui/Paginacion"
import { SkeletonCard, SkeletonStatCard } from "@/components/ui/skeleton"
import { fmtFechaHora, type Page } from "@/features/clientes/types"
import { JornadaDetalleModal } from "@/features/ventas/JornadaDetalleModal"
import {
  METODOS,
  METODO_LABEL,
  soles,
  type Arqueo,
  type MetodoPago,
  type Sesion,
} from "@/features/ventas/types"

/** El historial va debajo del arqueo del día, así que se muestra corto. */
const SESIONES_PAGE_SIZE = 15

export default function CajaPage() {
  const qc = useQueryClient()
  const canAbrir = usePermission("caja.abrir")
  const canCerrar = usePermission("caja.cerrar")
  const canMover = usePermission("caja.crear")

  const [sesionesPage, setSesionesPage] = useState(1)
  const [desde, setDesde] = useState("")
  const [hasta, setHasta] = useState("")
  const [sesionVista, setSesionVista] = useState<string | null>(null)
  const [abrirOpen, setAbrirOpen] = useState(false)
  const [cerrarOpen, setCerrarOpen] = useState(false)
  const [movOpen, setMovOpen] = useState(false)

  const [montoInicial, setMontoInicial] = useState("0")
  const [contado, setContado] = useState("")
  const [obsCierre, setObsCierre] = useState("")
  const [mov, setMov] = useState({
    tipo: "EGRESO",
    metodo: "EFECTIVO" as MetodoPago,
    monto: "",
    concepto: "",
  })

  const actual = useQuery({
    queryKey: ["caja", "actual"],
    queryFn: async () => (await api.get<Arqueo | null>(`${API_PREFIX}/caja/actual`)).data,
  })

  const sesiones = useQuery({
    queryKey: ["caja", "sesiones", { sesionesPage, desde, hasta }],
    queryFn: async () =>
      (
        await api.get<Page<Sesion>>(`${API_PREFIX}/caja/sesiones`, {
          params: {
            desde: desde || undefined,
            hasta: hasta || undefined,
            page: sesionesPage,
            page_size: SESIONES_PAGE_SIZE,
          },
        })
      ).data,
    placeholderData: (prev) => prev,
  })

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ["caja"] })
  }

  const abrir = useMutation({
    mutationFn: async () => {
      await api.post(`${API_PREFIX}/caja/abrir`, { monto_inicial: Number(montoInicial) || 0 })
    },
    onSuccess: () => {
      invalidar()
      setAbrirOpen(false)
    },
  })

  const cerrar = useMutation({
    mutationFn: async () => {
      await api.post(`${API_PREFIX}/caja/cerrar`, {
        monto_declarado: Number(contado) || 0,
        observaciones: obsCierre.trim() || null,
      })
    },
    onSuccess: () => {
      invalidar()
      setCerrarOpen(false)
      setContado("")
      setObsCierre("")
    },
  })

  const crearMov = useMutation({
    mutationFn: async () => {
      await api.post(`${API_PREFIX}/caja/movimientos`, {
        tipo: mov.tipo,
        metodo: mov.metodo,
        monto: Number(mov.monto) || 0,
        concepto: mov.concepto,
      })
    },
    onSuccess: () => {
      invalidar()
      setMovOpen(false)
      setMov({ tipo: "EGRESO", metodo: "EFECTIVO", monto: "", concepto: "" })
    },
  })

  const caja = actual.data
  const esperado = Number(caja?.efectivo_esperado ?? 0)
  const diferencia = contado === "" ? null : Number(contado) - esperado

  return (
    <div>
      <PageHeader
        title="Caja"
        description="Apertura, movimientos y arqueo del cajón."
        actions={
          caja ? (
            <div className="flex gap-2">
              {canMover && (
                <Button variant="secondary" onClick={() => setMovOpen(true)}>
                  <Plus className="h-4 w-4" />
                  Movimiento
                </Button>
              )}
              {canCerrar && (
                <Button onClick={() => setCerrarOpen(true)}>
                  <Lock className="h-4 w-4" />
                  Cerrar caja
                </Button>
              )}
            </div>
          ) : (
            canAbrir && (
              <Button onClick={() => setAbrirOpen(true)}>
                <LockOpen className="h-4 w-4" />
                Abrir caja
              </Button>
            )
          )
        }
      />

      {actual.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-3">
          <SkeletonStatCard />
          <SkeletonStatCard />
          <SkeletonStatCard />
        </div>
      ) : !caja ? (
        <div className="rounded-lg border border-dashed border-border py-16 text-center">
          <Wallet className="mx-auto h-10 w-10 text-muted-foreground" />
          <h2 className="mt-4 text-base font-semibold">La caja está cerrada</h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Ábrela con el monto con el que empiezas el día. Sin caja abierta sólo se pueden
            cobrar ventas con métodos digitales.
          </p>
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-lg border border-border bg-card p-5">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Efectivo en caja
              </p>
              <p className="tabular mt-3 text-2xl font-semibold">{soles(esperado)}</p>
              <p className="mt-1 text-xs text-muted-foreground">esperado ahora mismo</p>
            </div>
            <div className="rounded-lg border border-border bg-card p-5">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Monto inicial
              </p>
              <p className="tabular mt-3 text-2xl font-semibold">{soles(caja.monto_inicial)}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {fmtFechaHora(caja.fecha_apertura)}
              </p>
            </div>
            <div className="rounded-lg border border-border bg-card p-5">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Ventas
              </p>
              <p className="tabular mt-3 text-2xl font-semibold">{caja.cantidad_ventas}</p>
              <p className="mt-1 text-xs text-muted-foreground">en esta jornada</p>
            </div>
            <div className="rounded-lg border border-border bg-card p-5">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Sesión
              </p>
              <p className="tabular mt-3 text-2xl font-semibold">{caja.numero}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {caja.usuario_apertura?.full_name ?? "—"}
              </p>
            </div>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-[320px_1fr]">
            <div className="rounded-lg border border-border bg-card p-5">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Por método de pago
              </h2>
              <table className="mt-3 w-full text-sm">
                <tbody>
                  {METODOS.map((m) => {
                    const t = caja.totales[m.value]
                    const neto = Number(t.ingresos) - Number(t.egresos)
                    return (
                      <tr key={m.value} className="border-t border-border">
                        <td className="py-2">
                          {m.label}
                          {!m.efectivo && (
                            <span className="ml-1.5 text-xs text-muted-foreground">
                              (no va al cajón)
                            </span>
                          )}
                        </td>
                        <td className="tabular py-2 text-right font-medium">{soles(neto)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              <p className="mt-3 text-xs text-muted-foreground">
                El arqueo compara sólo el efectivo: Yape, Plin, tarjeta y transferencia no pasan
                por el cajón físico.
              </p>
            </div>

            <div className="rounded-lg border border-border">
              <h2 className="border-b border-border px-5 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Movimientos de la jornada
              </h2>
              <div className="max-h-96 overflow-y-auto">
                <table className="w-full text-sm">
                  <tbody>
                    {caja.movimientos.map((m) => (
                      <tr key={m.id} className="border-b border-border last:border-0">
                        <td className="px-4 py-2.5">
                          <span
                            className={cn(
                              "inline-flex items-center gap-1 text-xs font-medium",
                              m.tipo === "INGRESO" ? "text-state-success" : "text-state-danger",
                            )}
                          >
                            {m.tipo === "INGRESO" ? (
                              <ArrowUpRight className="h-3 w-3" />
                            ) : (
                              <ArrowDownRight className="h-3 w-3" />
                            )}
                            {METODO_LABEL[m.metodo]}
                          </span>
                          <div className="mt-0.5">{m.concepto}</div>
                          <div className="tabular text-xs text-muted-foreground">
                            {fmtFechaHora(m.created_at)}
                            {m.usuario && ` · ${m.usuario.full_name}`}
                          </div>
                        </td>
                        <td
                          className={cn(
                            "tabular px-4 py-2.5 text-right font-medium",
                            m.tipo === "INGRESO" ? "text-state-success" : "text-state-danger",
                          )}
                        >
                          {m.tipo === "INGRESO" ? "+" : "−"}
                          {soles(m.monto)}
                        </td>
                      </tr>
                    ))}
                    {caja.movimientos.length === 0 && (
                      <tr>
                        <td className="px-4 py-10 text-center text-sm text-muted-foreground">
                          Sin movimientos todavía.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}

      {/* -------------------- Historial -------------------- */}
      <div className="mt-8 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Jornadas anteriores
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Abre una jornada para ver las ventas que se cobraron ese día y su cuadre.
          </p>
        </div>

        <div className="flex flex-wrap items-end gap-2 text-sm">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">Desde</span>
            <input
              type="date"
              value={desde}
              max={hasta || undefined}
              onChange={(e) => {
                setDesde(e.target.value)
                setSesionesPage(1)
              }}
              className="rounded-md border border-border bg-background px-2 py-1.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">Hasta</span>
            <input
              type="date"
              value={hasta}
              min={desde || undefined}
              onChange={(e) => {
                setHasta(e.target.value)
                setSesionesPage(1)
              }}
              className="rounded-md border border-border bg-background px-2 py-1.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </label>
          {(desde || hasta) && (
            <Button
              variant="ghost"
              onClick={() => {
                setDesde("")
                setHasta("")
                setSesionesPage(1)
              }}
            >
              Limpiar
            </Button>
          )}
        </div>
      </div>
      {sesiones.isLoading ? (
        <SkeletonCard className="mt-3" />
      ) : (
        <div className={sesiones.isFetching ? "opacity-60 transition-opacity" : undefined}>
          <div className="mt-3 overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-secondary">
                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-2.5">Sesión</th>
                  <th className="px-4 py-2.5">Apertura</th>
                  <th className="px-4 py-2.5">Cierre</th>
                  <th className="px-4 py-2.5 text-right">Inicial</th>
                  <th className="px-4 py-2.5 text-right">Esperado</th>
                  <th className="px-4 py-2.5 text-right">Contado</th>
                  <th className="px-4 py-2.5 text-right">Diferencia</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {(sesiones.data?.items ?? []).map((s, i) => {
                  const dif = s.diferencia === null ? null : Number(s.diferencia)
                  return (
                    <tr
                      key={s.id}
                      onClick={() => setSesionVista(s.id)}
                      className={cn(
                        "cursor-pointer border-t border-border hover:bg-accent/50",
                        i % 2 === 1 && "bg-muted/30",
                      )}
                    >
                      <td className="tabular px-4 py-2.5 font-medium">
                        {s.numero}
                        <div>
                          <Badge tone={s.estado === "ABIERTA" ? "success" : "neutral"}>
                            {s.estado === "ABIERTA" ? "Abierta" : "Cerrada"}
                          </Badge>
                        </div>
                      </td>
                      <td className="tabular px-4 py-2.5 text-muted-foreground">
                        {fmtFechaHora(s.fecha_apertura)}
                        <div className="text-xs">{s.usuario_apertura?.full_name}</div>
                      </td>
                      <td className="tabular px-4 py-2.5 text-muted-foreground">
                        {s.fecha_cierre ? fmtFechaHora(s.fecha_cierre) : "—"}
                        <div className="text-xs">{s.usuario_cierre?.full_name}</div>
                      </td>
                      <td className="tabular px-4 py-2.5 text-right">{soles(s.monto_inicial)}</td>
                      <td className="tabular px-4 py-2.5 text-right text-muted-foreground">
                        {s.monto_esperado === null ? "—" : soles(s.monto_esperado)}
                      </td>
                      <td className="tabular px-4 py-2.5 text-right">
                        {s.monto_declarado === null ? "—" : soles(s.monto_declarado)}
                      </td>
                      <td className="tabular px-4 py-2.5 text-right">
                        {dif === null ? (
                          "—"
                        ) : (
                          <span
                            className={cn(
                              "font-medium",
                              Math.abs(dif) < 0.01
                                ? "text-state-success"
                                : dif > 0
                                  ? "text-state-info"
                                  : "text-state-danger",
                            )}
                          >
                            {dif > 0 ? "+" : ""}
                            {soles(dif)}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                          Ver ventas
                          <ChevronRight className="h-3.5 w-3.5" />
                        </span>
                      </td>
                    </tr>
                  )
                })}
                {(sesiones.data?.total ?? 0) === 0 && (
                  <tr>
                    <td colSpan={8} className="px-4 py-10 text-center text-sm text-muted-foreground">
                      {desde || hasta
                        ? "No hubo jornadas de caja en esas fechas."
                        : "Todavía no se ha cerrado ninguna jornada."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <Paginacion
            page={sesionesPage}
            pageSize={SESIONES_PAGE_SIZE}
            total={sesiones.data?.total ?? 0}
            onChange={setSesionesPage}
            etiqueta="jornadas"
          />
        </div>
      )}

      {/* -------------------- Modales -------------------- */}
      <JornadaDetalleModal sesionId={sesionVista} onClose={() => setSesionVista(null)} />

      <Modal
        open={abrirOpen}
        onClose={() => setAbrirOpen(false)}
        title="Abrir caja"
        description="Cuenta el efectivo con el que empiezas la jornada."
      >
        <Field label="Monto inicial (S/)" required>
          <Input
            autoFocus
            type="number"
            min="0"
            step="0.01"
            value={montoInicial}
            onChange={(e) => setMontoInicial(e.target.value)}
          />
        </Field>
        <div className="mt-4">
          <FormError message={abrir.isError ? apiErrorMessage(abrir.error) : null} />
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setAbrirOpen(false)}>
            Cancelar
          </Button>
          <Button disabled={abrir.isPending} onClick={() => abrir.mutate()}>
            {abrir.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Abrir caja
          </Button>
        </div>
      </Modal>

      <Modal
        open={cerrarOpen}
        onClose={() => setCerrarOpen(false)}
        title="Cerrar caja y arquear"
        description={`Sesión ${caja?.numero ?? ""}`}
      >
        <div className="rounded-md border border-border bg-muted/40 px-3 py-2.5 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Efectivo esperado</span>
            <span className="tabular font-semibold">{soles(esperado)}</span>
          </div>
        </div>

        <Field
          label="Efectivo contado (S/)"
          required
          className="mt-4"
          hint="Cuenta el cajón antes de mirar el esperado; así el arqueo sirve de control."
        >
          <Input
            autoFocus
            type="number"
            min="0"
            step="0.01"
            value={contado}
            onChange={(e) => setContado(e.target.value)}
          />
        </Field>

        {diferencia !== null && (
          <div
            className={cn(
              "mt-3 rounded-md border px-3 py-2.5 text-sm",
              Math.abs(diferencia) < 0.01
                ? "border-state-success/30 bg-state-success/10 text-state-success"
                : "border-state-warning/30 bg-state-warning/10 text-state-warning",
            )}
          >
            {Math.abs(diferencia) < 0.01
              ? "La caja cuadra exactamente."
              : diferencia > 0
                ? `Sobran ${soles(diferencia)} respecto a lo esperado.`
                : `Faltan ${soles(-diferencia)} respecto a lo esperado.`}
          </div>
        )}

        <Field label="Observaciones" className="mt-3">
          <Textarea
            rows={2}
            value={obsCierre}
            onChange={(e) => setObsCierre(e.target.value)}
            placeholder="Explica la diferencia si la hubo"
          />
        </Field>

        <div className="mt-4">
          <FormError message={cerrar.isError ? apiErrorMessage(cerrar.error) : null} />
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setCerrarOpen(false)}>
            Cancelar
          </Button>
          <Button disabled={cerrar.isPending || contado === ""} onClick={() => cerrar.mutate()}>
            {cerrar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Cerrar caja
          </Button>
        </div>
      </Modal>

      <Modal
        open={movOpen}
        onClose={() => setMovOpen(false)}
        title="Movimiento de caja"
        description="Retiro a banco, pago a proveedor, ingreso extra."
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Tipo" required>
            <Select value={mov.tipo} onChange={(e) => setMov({ ...mov, tipo: e.target.value })}>
              <option value="EGRESO">Egreso (sale dinero)</option>
              <option value="INGRESO">Ingreso (entra dinero)</option>
            </Select>
          </Field>
          <Field label="Método" required>
            <Select
              value={mov.metodo}
              onChange={(e) => setMov({ ...mov, metodo: e.target.value as MetodoPago })}
            >
              {METODOS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <Field label="Monto (S/)" required className="mt-3">
          <Input
            type="number"
            min="0"
            step="0.01"
            value={mov.monto}
            onChange={(e) => setMov({ ...mov, monto: e.target.value })}
          />
        </Field>

        <Field label="Concepto" required className="mt-3">
          <Input
            value={mov.concepto}
            onChange={(e) => setMov({ ...mov, concepto: e.target.value })}
            placeholder="Retiro a banco"
          />
        </Field>

        <div className="mt-4">
          <FormError message={crearMov.isError ? apiErrorMessage(crearMov.error) : null} />
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setMovOpen(false)}>
            Cancelar
          </Button>
          <Button
            disabled={crearMov.isPending || !mov.monto || mov.concepto.trim().length < 2}
            onClick={() => crearMov.mutate()}
          >
            {crearMov.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Registrar
          </Button>
        </div>
      </Modal>
    </div>
  )
}
