import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import {
  ArrowUpRight,
  Bike,
  ClipboardList,
  Package,
  ShoppingCart,
  TrendingUp,
  Users,
  Wallet,
} from "lucide-react"

import { api, API_PREFIX } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { cn, fechaLocal } from "@/lib/utils"
import { SkeletonChart, SkeletonStatCard, SkeletonTable } from "@/components/ui/skeleton"
import { soles } from "@/features/ventas/types"

type Tono = "rojo" | "azul" | "verde" | "ambar"

const TONO_ICONO: Record<Tono, string> = {
  rojo: "bg-primary/10 text-primary",
  azul: "bg-state-info/12 text-state-info",
  verde: "bg-state-success/12 text-state-success",
  ambar: "bg-state-warning/12 text-state-warning",
}

function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  tono = "rojo",
}: {
  label: string
  value: number | string
  hint: string
  icon: typeof Users
  tono?: Tono
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-5 transition hover:shadow-sm">
      <div className="flex items-start justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </span>
        <span className={cn("rounded-lg p-2", TONO_ICONO[tono])}>
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <p className="tabular mt-4 text-3xl font-bold tracking-tight">{value}</p>
      <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
    </div>
  )
}

export default function DashboardPage() {
  const me = useAuth((s) => s.me)
  const granted = new Set(me?.permission_codes ?? [])
  const canSeeClientes = granted.has("clientes.ver")
  const canSeeBicis = granted.has("bicicletas.ver")
  const canSeeVentas = granted.has("ventas.ver")
  const canSeeReportes = granted.has("reportes.ver")

  const clientesQ = useQuery({
    queryKey: ["clientes", "kpi"],
    queryFn: async () =>
      (await api.get<{ total: number }>(`${API_PREFIX}/clientes`, {
        params: { is_active: true, page_size: 1 },
      })).data.total,
    enabled: canSeeClientes,
  })
  const bicisQ = useQuery({
    queryKey: ["bicicletas", "kpi"],
    queryFn: async () =>
      (await api.get<{ total: number }>(`${API_PREFIX}/bicicletas`, {
        params: { is_active: true, page_size: 1 },
      })).data.total,
    enabled: canSeeBicis,
  })
  const ventasQ = useQuery({
    queryKey: ["ventas", "resumen-dia"],
    queryFn: async () =>
      (
        await api.get<{ cantidad: number; total: string; ticket_promedio: string }>(
          `${API_PREFIX}/ventas/resumen/dia`,
        )
      ).data,
    enabled: canSeeVentas,
  })

  // `toISOString()` da la fecha en UTC: pasadas las 7 p. m. en Lima devolvía
  // el día siguiente y el rango del gráfico se corría un día.
  const hoy = fechaLocal(new Date())
  const hace30 = fechaLocal(new Date(Date.now() - 29 * 86400000))

  const ingresosQ = useQuery({
    queryKey: ["reportes", "ventas", "dashboard"],
    queryFn: async () =>
      (
        await api.get<{ total: string; por_dia: { fecha: string; cantidad: number; total: string }[] }>(
          `${API_PREFIX}/reportes/ventas`,
          { params: { desde: hace30, hasta: hoy } },
        )
      ).data,
    enabled: canSeeReportes,
  })
  const masVendidosQ = useQuery({
    queryKey: ["reportes", "productos", "dashboard"],
    queryFn: async () =>
      (
        await api.get<{
          items: { sku: string | null; descripcion: string; cantidad: string; importe: string }[]
        }>(`${API_PREFIX}/reportes/productos-vendidos`, {
          params: { desde: hace30, hasta: hoy, limite: 5 },
        })
      ).data,
    enabled: canSeeReportes,
  })

  const isLoading =
    (canSeeClientes && clientesQ.isLoading) ||
    (canSeeBicis && bicisQ.isLoading) ||
    (canSeeVentas && ventasQ.isLoading)

  const porDia = ingresosQ.data?.por_dia ?? []
  const maxDia = Math.max(1, ...porDia.map((d) => Number(d.total)))
  const mejorDia = porDia.reduce(
    (mejor, d) => (Number(d.total) > Number(mejor?.total ?? 0) ? d : mejor),
    porDia[0],
  )

  const fecha = new Date().toLocaleDateString("es-PE", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  })

  // Accesos rápidos según permisos.
  const acciones = [
    { to: "/ventas/nueva", label: "Nueva venta", icon: ShoppingCart, perm: "ventas.crear" },
    { to: "/fichas/nueva", label: "Nueva ficha", icon: ClipboardList, perm: "fichas.crear" },
    { to: "/clientes", label: "Nuevo cliente", icon: Users, perm: "clientes.crear" },
  ].filter((a) => granted.has(a.perm))

  return (
    <div>
      {/* -------------------- Encabezado -------------------- */}
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Hola, {me?.full_name.split(" ")[0] ?? ""}
          </h1>
          <p className="mt-0.5 text-sm capitalize text-muted-foreground">{fecha}</p>
        </div>
        {acciones.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {acciones.map((a) => (
              <Link
                key={a.to}
                to={a.to}
                className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm font-medium transition hover:border-primary/40 hover:bg-accent"
              >
                <a.icon className="h-4 w-4 text-primary" />
                {a.label}
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* -------------------- KPIs -------------------- */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {isLoading ? (
          <>
            <SkeletonStatCard />
            <SkeletonStatCard />
            <SkeletonStatCard />
            <SkeletonStatCard />
          </>
        ) : (
          <>
            {canSeeVentas && (
              <>
                <StatCard
                  label="Ingresos de hoy"
                  value={soles(ventasQ.data?.total ?? 0)}
                  hint="ventas confirmadas"
                  icon={Wallet}
                  tono="verde"
                />
                <StatCard
                  label="Ventas de hoy"
                  value={ventasQ.data?.cantidad ?? 0}
                  hint={`ticket promedio ${soles(ventasQ.data?.ticket_promedio ?? 0)}`}
                  icon={ShoppingCart}
                  tono="rojo"
                />
              </>
            )}
            {canSeeClientes && (
              <StatCard
                label="Clientes activos"
                value={clientesQ.data ?? 0}
                hint="en el directorio"
                icon={Users}
                tono="azul"
              />
            )}
            {canSeeBicis && (
              <StatCard
                label="Bicicletas activas"
                value={bicisQ.data ?? 0}
                hint="registradas en el sistema"
                icon={Bike}
                tono="ambar"
              />
            )}
            {!canSeeClientes && !canSeeBicis && !canSeeVentas && (
              <div className="rounded-xl border border-border bg-card p-5 sm:col-span-2 xl:col-span-4">
                <p className="text-sm font-medium">Tu rol: {me?.role.name}</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Tienes {me?.permission_codes.length} permisos asignados. Los módulos disponibles
                  aparecen en el menú lateral.
                </p>
              </div>
            )}
          </>
        )}
      </div>

      {/* -------------------- Gráfico + ranking -------------------- */}
      {canSeeReportes && (
        <div className="mt-6 grid gap-4 lg:grid-cols-5">
          {/* Ingresos por día */}
          <div className="lg:col-span-3">
            {ingresosQ.isLoading || !ingresosQ.data ? (
              <SkeletonChart />
            ) : (
              <div className="h-full rounded-xl border border-border bg-card p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="flex items-center gap-2 text-sm font-semibold">
                      <TrendingUp className="h-4 w-4 text-primary" />
                      Ingresos · últimos 30 días
                    </h2>
                    <p className="tabular mt-1 text-2xl font-bold tracking-tight">
                      {soles(ingresosQ.data.total)}
                    </p>
                    {mejorDia && Number(mejorDia.total) > 0 && (
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        Mejor día: {mejorDia.fecha.slice(5)} · {soles(mejorDia.total)}
                      </p>
                    )}
                  </div>
                  <Link
                    to="/reportes"
                    className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                  >
                    Ver reportes <ArrowUpRight className="h-3 w-3" />
                  </Link>
                </div>

                <div className="mt-5 flex h-44 items-end gap-1">
                  {porDia.map((d) => (
                    <div
                      key={d.fecha}
                      className="group relative flex h-full flex-1 flex-col justify-end"
                      title={`${d.fecha}: ${soles(d.total)} (${d.cantidad} ventas)`}
                    >
                      <div
                        className="w-full rounded-t-sm bg-primary/70 transition group-hover:bg-primary"
                        style={{ height: `${Math.max((Number(d.total) / maxDia) * 100, 1)}%` }}
                      />
                    </div>
                  ))}
                </div>
                <div className="mt-2 flex justify-between border-t border-border pt-2 text-[10px] text-muted-foreground">
                  <span>{porDia[0]?.fecha.slice(5)}</span>
                  <span>{porDia.at(-1)?.fecha.slice(5)}</span>
                </div>
                {Number(maxDia) <= 1 && (
                  <p className="mt-2 text-center text-xs text-muted-foreground">
                    Aún no hay ventas en el periodo.
                  </p>
                )}
              </div>
            )}
          </div>

          {/* Productos más vendidos */}
          <div className="lg:col-span-2">
            {masVendidosQ.isLoading || !masVendidosQ.data ? (
              <SkeletonTable rows={5} headers={["Producto", "Total"]} />
            ) : (
              <div className="h-full rounded-xl border border-border bg-card p-5">
                <div className="flex items-center justify-between">
                  <h2 className="flex items-center gap-2 text-sm font-semibold">
                    <Package className="h-4 w-4 text-primary" />
                    Más vendidos
                  </h2>
                  <Link
                    to="/reportes"
                    className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                  >
                    Ver todo <ArrowUpRight className="h-3 w-3" />
                  </Link>
                </div>

                {masVendidosQ.data.items.length === 0 ? (
                  <p className="mt-8 text-center text-sm text-muted-foreground">
                    Sin ventas en los últimos 30 días.
                  </p>
                ) : (
                  <ul className="mt-4 space-y-3">
                    {masVendidosQ.data.items.map((p, i) => (
                      <li key={`${p.sku}-${i}`} className="flex items-center gap-3">
                        <span className="tabular flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-muted text-xs font-semibold text-muted-foreground">
                          {i + 1}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium">{p.descripcion}</p>
                          <p className="tabular text-xs text-muted-foreground">
                            {Number(p.cantidad)} vendidos
                          </p>
                        </div>
                        <span className="tabular shrink-0 text-sm font-semibold">
                          {soles(p.importe)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
