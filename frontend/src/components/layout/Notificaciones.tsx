import { useEffect, useRef, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { AlertTriangle, Bell, CheckCircle2, Info } from "lucide-react"

import { api, API_PREFIX } from "@/lib/api"
import { cn } from "@/lib/utils"

type Alerta = {
  tipo: string
  nivel: "info" | "warning" | "danger"
  titulo: string
  detalle: string
  enlace: string
  cantidad: number
}
type Respuesta = { total: number; alertas: Alerta[] }

const ICONO = { info: Info, warning: AlertTriangle, danger: AlertTriangle } as const
const COLOR = {
  info: "text-state-info",
  warning: "text-state-warning",
  danger: "text-state-danger",
} as const

export function Notificaciones() {
  const navigate = useNavigate()
  const [abierto, setAbierto] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const { data } = useQuery({
    queryKey: ["notificaciones"],
    queryFn: async () =>
      (await api.get<Respuesta>(`${API_PREFIX}/notificaciones`)).data,
    // Refresca en segundo plano: las alertas reflejan el estado del negocio.
    refetchInterval: 60_000,
  })

  useEffect(() => {
    const fuera = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setAbierto(false)
    }
    document.addEventListener("mousedown", fuera)
    return () => document.removeEventListener("mousedown", fuera)
  }, [])

  const alertas = data?.alertas ?? []
  const cantidad = alertas.length

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setAbierto((v) => !v)}
        className="relative rounded-md border border-border p-2 text-muted-foreground hover:bg-accent hover:text-foreground"
        aria-label="Notificaciones"
      >
        <Bell className="h-4 w-4" />
        {cantidad > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-bold text-white">
            {cantidad}
          </span>
        )}
      </button>

      {abierto && (
        <div className="absolute right-0 z-50 mt-2 w-80 rounded-lg border border-border bg-card shadow-lg">
          <div className="border-b border-border px-4 py-2.5">
            <h3 className="text-sm font-semibold">Notificaciones</h3>
          </div>

          {alertas.length === 0 ? (
            <div className="px-4 py-8 text-center">
              <CheckCircle2 className="mx-auto h-8 w-8 text-state-success/60" />
              <p className="mt-2 text-sm text-muted-foreground">Todo en orden. Sin alertas.</p>
            </div>
          ) : (
            <ul className="max-h-96 overflow-y-auto">
              {alertas.map((a) => {
                const Icono = ICONO[a.nivel]
                return (
                  <li key={a.tipo}>
                    <button
                      onClick={() => {
                        setAbierto(false)
                        navigate(a.enlace)
                      }}
                      className="flex w-full items-start gap-3 border-b border-border px-4 py-3 text-left last:border-0 hover:bg-accent"
                    >
                      <Icono className={cn("mt-0.5 h-4 w-4 shrink-0", COLOR[a.nivel])} />
                      <div className="min-w-0">
                        <p className="text-sm font-medium">{a.titulo}</p>
                        <p className="text-xs text-muted-foreground">{a.detalle}</p>
                      </div>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
