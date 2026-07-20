import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Search } from "lucide-react"

import { api, API_PREFIX } from "@/lib/api"
import { Badge } from "@/components/ui/Badge"
import { Select } from "@/components/ui/Form"
import { PageHeader } from "@/components/ui/PageHeader"
import { Paginacion } from "@/components/ui/Paginacion"
import { SkeletonTable } from "@/components/ui/skeleton"
import { fmtFechaHora, type Page } from "@/features/clientes/types"

const PAGE_SIZE = 50

type Registro = {
  id: string
  created_at: string
  usuario_email: string | null
  metodo: string
  ruta: string
  entidad: string | null
  status_code: number
  duracion_ms: number
  ip: string | null
}

const METODO_TONE: Record<string, "success" | "info" | "warning" | "danger"> = {
  POST: "success",
  PATCH: "info",
  PUT: "info",
  DELETE: "danger",
}

const ENTIDADES = [
  "clientes",
  "bicicletas",
  "fichas",
  "inventario",
  "ventas",
  "caja",
  "facturacion",
  "usuarios",
  "roles",
  "auth",
]

export default function AuditoriaPage() {
  const [entidad, setEntidad] = useState("")
  const [email, setEmail] = useState("")
  const [debounced, setDebounced] = useState("")
  const [soloErrores, setSoloErrores] = useState(false)
  const [page, setPage] = useState(1)

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(email)
      setPage(1)
    }, 300)
    return () => clearTimeout(t)
  }, [email])

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["auditoria", { entidad, debounced, soloErrores, page }],
    queryFn: async () =>
      (
        await api.get<Page<Registro>>(`${API_PREFIX}/auditoria`, {
          params: {
            entidad: entidad || undefined,
            usuario_email: debounced || undefined,
            solo_errores: soloErrores || undefined,
            page,
            page_size: PAGE_SIZE,
          },
        })
      ).data,
    placeholderData: (prev) => prev,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div>
      <PageHeader
        title="Auditoría"
        description="Bitácora de acciones que cambian el estado del sistema."
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Select
          value={entidad}
          onChange={(e) => {
            setEntidad(e.target.value)
            setPage(1)
          }}
          className="w-44 py-1.5"
        >
          <option value="">Todos los módulos</option>
          {ENTIDADES.map((e) => (
            <option key={e} value={e}>
              {e}
            </option>
          ))}
        </Select>

        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Filtrar por usuario..."
            className="w-56 rounded-md border border-border bg-background py-1.5 pl-8 pr-3 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>

        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={soloErrores}
            onChange={(e) => {
              setSoloErrores(e.target.checked)
              setPage(1)
            }}
            className="h-3.5 w-3.5 accent-[var(--primary)]"
          />
          Sólo errores (4xx/5xx)
        </label>
      </div>

      {isLoading ? (
        <SkeletonTable
          rows={12}
          headers={["Fecha", "Usuario", "Acción", "Módulo", "Estado", "Duración", "IP"]}
          columns={["w-36", "w-44", "w-40", "w-24", "w-16", "w-16", "w-24"]}
        />
      ) : (
        <div className={isFetching ? "opacity-60 transition-opacity" : "transition-opacity"}>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-secondary">
                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-2.5">Fecha</th>
                  <th className="px-4 py-2.5">Usuario</th>
                  <th className="px-4 py-2.5">Acción</th>
                  <th className="px-4 py-2.5">Módulo</th>
                  <th className="px-4 py-2.5 text-right">Estado</th>
                  <th className="px-4 py-2.5 text-right">Duración</th>
                  <th className="px-4 py-2.5">IP</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r, i) => (
                  <tr
                    key={r.id}
                    className={
                      i % 2 === 1 ? "border-t border-border bg-muted/30" : "border-t border-border"
                    }
                  >
                    <td className="tabular px-4 py-2 text-muted-foreground">
                      {fmtFechaHora(r.created_at)}
                    </td>
                    <td className="px-4 py-2">{r.usuario_email ?? "—"}</td>
                    <td className="px-4 py-2">
                      <span className="flex items-center gap-2">
                        <Badge tone={METODO_TONE[r.metodo] ?? "neutral"}>{r.metodo}</Badge>
                        <code className="tabular text-xs text-muted-foreground">{r.ruta}</code>
                      </span>
                    </td>
                    <td className="px-4 py-2 text-muted-foreground">{r.entidad ?? "—"}</td>
                    <td className="px-4 py-2 text-right">
                      <span
                        className={
                          r.status_code >= 400
                            ? "tabular font-medium text-state-danger"
                            : "tabular text-state-success"
                        }
                      >
                        {r.status_code}
                      </span>
                    </td>
                    <td className="tabular px-4 py-2 text-right text-muted-foreground">
                      {r.duracion_ms} ms
                    </td>
                    <td className="tabular px-4 py-2 text-muted-foreground">{r.ip ?? "—"}</td>
                  </tr>
                ))}
                {items.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-12 text-center text-sm text-muted-foreground">
                      Sin registros con estos filtros.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <Paginacion
            page={page}
            pageSize={PAGE_SIZE}
            total={total}
            onChange={setPage}
            etiqueta="registros"
          />
        </div>
      )}
    </div>
  )
}
