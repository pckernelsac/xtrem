import { useEffect, useState } from "react"
import { Outlet, useLocation, useNavigate } from "react-router-dom"
import { LogOut, Menu, Moon, Sun } from "lucide-react"

import { useAuth } from "@/lib/auth"
import { useTheme } from "@/lib/theme"
import { Notificaciones } from "./Notificaciones"
import { Sidebar } from "./Sidebar"

/** `true` a partir de `lg`, el ancho donde el menú cabe junto al contenido. */
function useEsEscritorio() {
  const [esEscritorio, setEsEscritorio] = useState(
    () => window.matchMedia("(min-width: 1024px)").matches,
  )

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)")
    const alCambiar = (e: MediaQueryListEvent) => setEsEscritorio(e.matches)
    mq.addEventListener("change", alCambiar)
    return () => mq.removeEventListener("change", alCambiar)
  }, [])

  return esEscritorio
}

export function AppLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const [menuMovil, setMenuMovil] = useState(false)
  const esEscritorio = useEsEscritorio()
  const { me, logout } = useAuth()
  const { theme, setTheme } = useTheme()
  const navigate = useNavigate()
  const { pathname } = useLocation()

  // Navegar cierra el cajón: en el móvil tapa toda la pantalla y dejarlo
  // abierto escondería la página a la que se acaba de entrar.
  useEffect(() => setMenuMovil(false), [pathname])

  useEffect(() => {
    if (!menuMovil) return
    const alPulsar = (e: KeyboardEvent) => e.key === "Escape" && setMenuMovil(false)
    window.addEventListener("keydown", alPulsar)
    return () => window.removeEventListener("keydown", alPulsar)
  }, [menuMovil])

  const initials = (me?.full_name ?? "")
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase()

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Velo del cajón. Sólo existe en móvil y con el menú abierto. No es
          botón ni tiene rótulo: cerrar ya está en la X y en Escape, y un
          segundo "Cerrar menú" sólo duplicaría el anuncio del lector. */}
      {menuMovil && (
        <div
          onClick={() => setMenuMovil(false)}
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          aria-hidden
        />
      )}

      <Sidebar
        // En móvil el cajón siempre se muestra ancho: un riel de iconos sobre
        // el velo ocuparía toda la pantalla para mostrar la mitad de la info.
        collapsed={esEscritorio ? collapsed : false}
        onToggle={() => setCollapsed((v) => !v)}
        abierto={menuMovil}
        onCerrar={() => setMenuMovil(false)}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-border bg-card px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <button
              onClick={() => setMenuMovil(true)}
              className="-ml-1 rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground lg:hidden"
              aria-label="Abrir menú"
            >
              <Menu className="h-5 w-5" />
            </button>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">{me?.full_name}</p>
              <p className="truncate text-xs text-muted-foreground">{me?.role.name}</p>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-1 sm:gap-2">
            <button
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              className="rounded-md border border-border p-2 text-muted-foreground hover:bg-accent hover:text-foreground"
              aria-label="Cambiar tema"
            >
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>

            <Notificaciones />

            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-white">
              {initials}
            </div>

            <button
              onClick={() => {
                logout()
                navigate("/login", { replace: true })
              }}
              className="rounded-md border border-border p-2 text-muted-foreground hover:bg-accent hover:text-foreground"
              aria-label="Cerrar sesión"
              title="Cerrar sesión"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-4 sm:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
