import { NavLink } from "react-router-dom"
import {
  Bike,
  ChevronsLeft,
  ChevronsRight,
  ClipboardList,
  FileSpreadsheet,
  FileText,
  LayoutDashboard,
  Package,
  Receipt,
  ScrollText,
  ShieldCheck,
  ShoppingCart,
  Users,
  Wallet,
  X,
} from "lucide-react"

import { cn } from "@/lib/utils"
import { useAuth } from "@/lib/auth"

type NavItem = {
  to: string
  label: string
  /** Rótulo corto para el riel plegado, donde no caben dos palabras largas. */
  corto?: string
  icon: typeof LayoutDashboard
  permission: string
  soon?: boolean
}

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", corto: "Inicio", icon: LayoutDashboard, permission: "dashboard.ver" },
  { to: "/clientes", label: "Clientes", icon: Users, permission: "clientes.ver" },
  { to: "/bicicletas", label: "Bicicletas", corto: "Bicis", icon: Bike, permission: "bicicletas.ver" },
  { to: "/fichas", label: "Servicios", icon: ClipboardList, permission: "fichas.ver" },
  { to: "/inventario", label: "Inventario", icon: Package, permission: "inventario.ver" },
  { to: "/ventas", label: "Ventas", icon: ShoppingCart, permission: "ventas.ver" },
  { to: "/cotizaciones", label: "Cotizaciones", corto: "Cotiz.", icon: FileSpreadsheet, permission: "ventas.ver" },
  { to: "/caja", label: "Caja", icon: Wallet, permission: "caja.ver" },
  { to: "/documentos", label: "Documentos", corto: "Docs", icon: Receipt, permission: "facturacion.ver" },
  { to: "/reportes", label: "Reportes", icon: FileText, permission: "reportes.ver" },
  { to: "/usuarios", label: "Usuarios", icon: Users, permission: "usuarios.ver" },
  { to: "/roles", label: "Roles", icon: ShieldCheck, permission: "roles.ver" },
  { to: "/auditoria", label: "Auditoría", corto: "Auditoría", icon: ScrollText, permission: "auditoria.ver" },
]

export function Sidebar({
  collapsed,
  onToggle,
  abierto = false,
  onCerrar,
}: {
  collapsed: boolean
  onToggle: () => void
  /** Sólo en móvil: si el cajón está desplegado sobre el contenido. */
  abierto?: boolean
  onCerrar?: () => void
}) {
  const me = useAuth((s) => s.me)
  const granted = new Set(me?.permission_codes ?? [])
  // Un ítem que el usuario no puede abrir no se muestra: menos ruido y
  // ninguna promesa de acceso que el backend luego niegue con un 403.
  const items = NAV.filter((i) => granted.has(i.permission))

  return (
    // Panel flotante con esquinas redondeadas en vez de una columna pegada al
    // borde: separa visualmente la navegación del contenido de trabajo.
    // Bajo `lg` no hay ancho que repartir, así que sale del flujo y se
    // convierte en un cajón que entra deslizándose sobre el contenido.
    <aside
      className={cn(
        "fixed inset-y-3 left-3 z-40 flex w-60 flex-col rounded-2xl bg-sidebar shadow-lg ring-1 ring-white/5 transition-transform duration-200",
        "lg:static lg:my-3 lg:ml-3 lg:shrink-0 lg:translate-x-0 lg:transition-[width]",
        abierto ? "translate-x-0" : "translate-x-[-110%]",
        collapsed ? "lg:w-20" : "lg:w-60",
      )}
    >
      <div
        className={cn(
          "flex shrink-0 items-center gap-2 px-3 pb-2 pt-3",
          collapsed ? "flex-col" : "flex-row",
        )}
      >
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary text-sm font-bold text-white">
          ZX
        </div>
        {!collapsed && (
          <span className="truncate text-sm font-semibold text-white">Zona Xtrema</span>
        )}
        {/* En el cajón móvil plegar no tiene sentido: lo que se necesita es
            cerrarlo y volver al contenido. */}
        <button
          onClick={onCerrar}
          className="ml-auto rounded-lg p-1.5 text-sidebar-foreground transition-colors hover:bg-white/10 hover:text-white lg:hidden"
          aria-label="Cerrar menú"
        >
          <X className="h-4 w-4" />
        </button>

        <button
          onClick={onToggle}
          className={cn(
            "hidden rounded-lg p-1.5 text-sidebar-foreground transition-colors hover:bg-white/10 hover:text-white lg:block",
            !collapsed && "lg:ml-auto",
          )}
          aria-label={collapsed ? "Expandir menú" : "Colapsar menú"}
          title={collapsed ? "Expandir menú" : "Colapsar menú"}
        >
          {collapsed ? (
            <ChevronsRight className="h-4 w-4" />
          ) : (
            <ChevronsLeft className="h-4 w-4" />
          )}
        </button>
      </div>

      {/* `min-h-0` es lo que permite que el nav se encoja por debajo de su
          contenido: sin él, con 13 ítems el panel crece y se sale de pantalla
          en vez de desplazarse por dentro. */}
      <nav className="scrollbar-none min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 pb-2">
        {items.map(({ to, label, corto, icon: Icon, soon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            title={label}
            className={({ isActive }) =>
              cn(
                "group rounded-xl transition-colors",
                collapsed
                  ? "flex flex-col items-center gap-0.5 px-1 py-1.5"
                  : "flex items-center gap-3 px-3 py-2 text-sm",
                isActive
                  ? "text-white"
                  : "text-sidebar-foreground hover:bg-white/5 hover:text-white",
                // En modo ancho el resalte cubre toda la fila; en el riel sólo
                // el recuadro del icono, como una pastilla.
                isActive && !collapsed && "bg-primary font-medium",
              )
            }
          >
            {({ isActive }) => (
              <>
                <span
                  className={cn(
                    "flex items-center justify-center transition-colors",
                    collapsed
                      ? cn(
                          "h-9 w-9 rounded-xl",
                          isActive
                            ? "bg-primary/20 text-primary ring-1 ring-primary/50"
                            : "group-hover:bg-white/10",
                        )
                      : "",
                  )}
                >
                  <Icon className={collapsed ? "h-5 w-5" : "h-4 w-4 shrink-0"} />
                </span>

                {collapsed ? (
                  <span
                    className={cn(
                      "w-full text-center text-[10px] leading-tight",
                      isActive && "font-semibold text-white",
                    )}
                  >
                    {corto ?? label}
                  </span>
                ) : (
                  <>
                    <span className="truncate">{label}</span>
                    {soon && (
                      <span className="ml-auto rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] font-medium text-zinc-500">
                        pronto
                      </span>
                    )}
                  </>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
