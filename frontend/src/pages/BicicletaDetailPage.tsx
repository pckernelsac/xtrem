import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "react-router-dom"
import { ArrowLeft, ClipboardList, Pencil, User } from "lucide-react"

import { api, API_PREFIX } from "@/lib/api"
import { usePermission } from "@/lib/auth"
import { Badge } from "@/components/ui/Badge"
import { Button } from "@/components/ui/Form"
import { Paginacion, recortarPagina } from "@/components/ui/Paginacion"
import { SkeletonCard } from "@/components/ui/skeleton"
import { BicicletaFormModal } from "@/features/clientes/BicicletaFormModal"
import { fmtFechaHora, type BicicletaDetail } from "@/features/clientes/types"

function Dato({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="tabular mt-0.5 text-sm">{value || "—"}</dd>
    </div>
  )
}

/** El historial viene entero dentro del detalle, así que se recorta aquí: una
 *  bici con años de taller acumula decenas de eventos y la línea de tiempo
 *  crece sin fin. */
const HISTORIAL_PAGE_SIZE = 10

export default function BicicletaDetailPage() {
  const { id = "" } = useParams()
  const navigate = useNavigate()
  const canEdit = usePermission("bicicletas.editar")
  const [editOpen, setEditOpen] = useState(false)
  const [histPage, setHistPage] = useState(1)

  const { data: bici, isLoading } = useQuery({
    queryKey: ["bicicletas", id],
    queryFn: async () => (await api.get<BicicletaDetail>(`${API_PREFIX}/bicicletas/${id}`)).data,
    enabled: Boolean(id),
  })

  if (isLoading) {
    return (
      <div className="space-y-4">
        <SkeletonCard />
        <SkeletonCard className="h-48" />
      </div>
    )
  }

  if (!bici) {
    return (
      <div className="grid h-full place-items-center text-sm text-muted-foreground">
        Bicicleta no encontrada.
      </div>
    )
  }

  return (
    <div>
      <button
        onClick={() => navigate("/bicicletas")}
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Volver a bicicletas
      </button>

      <div className="rounded-lg border border-border bg-card p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-xl font-semibold">{bici.descripcion}</h1>
              <Badge tone={bici.is_active ? "success" : "neutral"}>
                {bici.is_active ? "Activa" : "Inactiva"}
              </Badge>
            </div>
            <Link
              to={`/clientes/${bici.cliente_id}`}
              className="mt-1 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary hover:underline"
            >
              <User className="h-3.5 w-3.5" />
              {bici.cliente.nombre} · {bici.cliente.tipo_documento} {bici.cliente.numero_documento}
            </Link>
          </div>

          {canEdit && (
            <Button variant="secondary" onClick={() => setEditOpen(true)}>
              <Pencil className="h-3.5 w-3.5" />
              Editar
            </Button>
          )}
        </div>

        <dl className="mt-5 grid gap-4 border-t border-border pt-4 sm:grid-cols-3 lg:grid-cols-4">
          <Dato label="Tipo" value={bici.tipo} />
          <Dato label="Marca" value={bici.marca} />
          <Dato label="Modelo" value={bici.modelo} />
          <Dato label="Color" value={bici.color} />
          <Dato label="N° de serie" value={bici.numero_serie} />
          <Dato label="Rodado" value={bici.rodado} />
          <Dato label="Talla" value={bici.talla} />
          <Dato label="Año" value={bici.anio} />
        </dl>

        {bici.notas && (
          <div className="mt-4 rounded-md bg-muted/50 px-3 py-2.5 text-sm">
            <span className="text-xs font-medium text-muted-foreground">Notas</span>
            <p className="mt-1 whitespace-pre-wrap">{bici.notas}</p>
          </div>
        )}
      </div>

      <h2 className="mt-6 text-sm font-semibold">Historial</h2>
      <div className="mt-3 rounded-lg border border-border bg-card p-5">
        <ol className="relative space-y-5 border-l border-border pl-5">
          {recortarPagina(bici.historial, histPage, HISTORIAL_PAGE_SIZE).map((ev, i) => (
            <li key={i} className="relative">
              <span className="absolute -left-[26px] top-1 flex h-3 w-3 items-center justify-center rounded-full border-2 border-card bg-primary" />
              <p className="text-sm font-medium">{ev.titulo}</p>
              {ev.detalle && <p className="text-sm text-muted-foreground">{ev.detalle}</p>}
              <p className="tabular mt-0.5 text-xs text-muted-foreground">
                {fmtFechaHora(ev.fecha)}
              </p>
            </li>
          ))}
        </ol>

        <Paginacion
          page={histPage}
          pageSize={HISTORIAL_PAGE_SIZE}
          total={bici.historial.length}
          onChange={setHistPage}
          etiqueta="eventos"
        />

        <div className="mt-5 flex items-start gap-2.5 rounded-md border border-dashed border-border px-3 py-2.5 text-xs text-muted-foreground">
          <ClipboardList className="mt-px h-3.5 w-3.5 shrink-0" />
          <span>
            Las fichas de mantenimiento (Fase 3) y las ventas de repuestos (Fase 5) se sumarán
            automáticamente a este historial.
          </span>
        </div>
      </div>

      <BicicletaFormModal
        open={editOpen}
        onClose={() => setEditOpen(false)}
        bicicleta={bici}
      />
    </div>
  )
}
