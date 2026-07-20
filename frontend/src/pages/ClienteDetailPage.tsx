import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "react-router-dom"
import { ArrowLeft, Bike, Mail, MapPin, Pencil, Phone, Plus, UserX } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { usePermission } from "@/lib/auth"
import { Badge } from "@/components/ui/Badge"
import { Button, FormError } from "@/components/ui/Form"
import { Modal } from "@/components/ui/Modal"
import { Paginacion, recortarPagina } from "@/components/ui/Paginacion"
import { SkeletonCard, SkeletonTable } from "@/components/ui/skeleton"
import { BicicletaFormModal } from "@/features/clientes/BicicletaFormModal"
import { ClienteFormModal } from "@/features/clientes/ClienteFormModal"
import { fmtFecha, type ClienteDetail } from "@/features/clientes/types"

/** El detalle del cliente ya trae todas sus bicicletas, así que la lista se
 *  recorta en el cliente: paginar aquí no ahorra ninguna consulta, sólo evita
 *  que un cliente de flota empuje el resto de la página fuera de la pantalla. */
const BICIS_PAGE_SIZE = 10

export default function ClienteDetailPage() {
  const { id = "" } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const canEdit = usePermission("clientes.editar")
  const canDelete = usePermission("clientes.eliminar")
  const canCreateBici = usePermission("bicicletas.crear")

  const [bicisPage, setBicisPage] = useState(1)
  const [editOpen, setEditOpen] = useState(false)
  const [biciOpen, setBiciOpen] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const { data: cliente, isLoading } = useQuery({
    queryKey: ["clientes", id],
    queryFn: async () => (await api.get<ClienteDetail>(`${API_PREFIX}/clientes/${id}`)).data,
    enabled: Boolean(id),
  })

  // Archivado, no borrado: el DELETE de la API elimina de verdad y se niega en
  // cuanto el cliente tenga fichas o ventas. Desde aquí la acción es dar de
  // baja, que es reversible; eliminar vive en el listado.
  const desactivar = useMutation({
    mutationFn: async () => {
      await api.patch(`${API_PREFIX}/clientes/${id}`, { is_active: false })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["clientes"] })
      setConfirmOpen(false)
    },
  })

  if (isLoading) {
    return (
      <div className="space-y-4">
        <SkeletonCard />
        <SkeletonTable rows={4} headers={["Bicicleta", "Tipo", "N° Serie", "Estado"]} />
      </div>
    )
  }

  if (!cliente) {
    return (
      <div className="grid h-full place-items-center text-sm text-muted-foreground">
        Cliente no encontrado.
      </div>
    )
  }

  return (
    <div>
      <button
        onClick={() => navigate("/clientes")}
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Volver a clientes
      </button>

      <div className="rounded-lg border border-border bg-card p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-xl font-semibold">{cliente.nombre}</h1>
              <Badge tone={cliente.is_active ? "success" : "neutral"}>
                {cliente.is_active ? "Activo" : "Archivado"}
              </Badge>
            </div>
            <p className="tabular mt-1 text-sm text-muted-foreground">
              {cliente.tipo_documento} {cliente.numero_documento} · Cliente desde{" "}
              {fmtFecha(cliente.created_at)}
            </p>
          </div>

          <div className="flex gap-2">
            {canEdit && (
              <Button variant="secondary" onClick={() => setEditOpen(true)}>
                <Pencil className="h-3.5 w-3.5" />
                Editar
              </Button>
            )}
            {canDelete && cliente.is_active && (
              <Button variant="danger" onClick={() => setConfirmOpen(true)}>
                <UserX className="h-3.5 w-3.5" />
                Archivar
              </Button>
            )}
          </div>
        </div>

        <div className="mt-5 grid gap-3 border-t border-border pt-4 text-sm sm:grid-cols-3">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Phone className="h-4 w-4 shrink-0" />
            <span className="tabular">{cliente.telefono || "Sin teléfono"}</span>
          </div>
          <div className="flex items-center gap-2 text-muted-foreground">
            <Mail className="h-4 w-4 shrink-0" />
            <span className="truncate">{cliente.email || "Sin correo"}</span>
          </div>
          <div className="flex items-center gap-2 text-muted-foreground">
            <MapPin className="h-4 w-4 shrink-0" />
            <span className="truncate">{cliente.direccion || "Sin dirección"}</span>
          </div>
        </div>

        {cliente.notas && (
          <div className="mt-4 rounded-md bg-muted/50 px-3 py-2.5 text-sm">
            <span className="text-xs font-medium text-muted-foreground">Notas internas</span>
            <p className="mt-1 whitespace-pre-wrap">{cliente.notas}</p>
          </div>
        )}
      </div>

      <div className="mt-6 flex items-center justify-between">
        <h2 className="text-sm font-semibold">
          Bicicletas <span className="tabular text-muted-foreground">({cliente.bicicletas.length})</span>
        </h2>
        {canCreateBici && cliente.is_active && (
          <Button variant="secondary" onClick={() => setBiciOpen(true)}>
            <Plus className="h-3.5 w-3.5" />
            Agregar bicicleta
          </Button>
        )}
      </div>

      <div className="mt-3 overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-secondary">
            <tr className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <th className="px-4 py-2.5">Bicicleta</th>
              <th className="px-4 py-2.5">Tipo</th>
              <th className="px-4 py-2.5">N° Serie</th>
              <th className="px-4 py-2.5">Estado</th>
            </tr>
          </thead>
          <tbody>
            {recortarPagina(cliente.bicicletas, bicisPage, BICIS_PAGE_SIZE).map((b, i) => (
              <tr
                key={b.id}
                className={i % 2 === 1 ? "border-t border-border bg-muted/30" : "border-t border-border"}
              >
                <td className="px-4 py-2.5">
                  <Link
                    to={`/bicicletas/${b.id}`}
                    className="inline-flex items-center gap-2 font-medium hover:text-primary hover:underline"
                  >
                    <Bike className="h-3.5 w-3.5 text-muted-foreground" />
                    {[b.marca, b.modelo, b.color].filter(Boolean).join(" ")}
                  </Link>
                </td>
                <td className="px-4 py-2.5 text-muted-foreground">{b.tipo}</td>
                <td className="tabular px-4 py-2.5 text-muted-foreground">
                  {b.numero_serie || "—"}
                </td>
                <td className="px-4 py-2.5">
                  <Badge tone={b.is_active ? "success" : "neutral"}>
                    {b.is_active ? "Activa" : "Inactiva"}
                  </Badge>
                </td>
              </tr>
            ))}
            {cliente.bicicletas.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center text-sm text-muted-foreground">
                  Este cliente aún no tiene bicicletas registradas.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <Paginacion
        page={bicisPage}
        pageSize={BICIS_PAGE_SIZE}
        total={cliente.bicicletas.length}
        onChange={setBicisPage}
        etiqueta="bicicletas"
      />

      <ClienteFormModal open={editOpen} onClose={() => setEditOpen(false)} cliente={cliente} />
      <BicicletaFormModal
        open={biciOpen}
        onClose={() => setBiciOpen(false)}
        clienteId={cliente.id}
      />

      <Modal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Archivar cliente"
        description={cliente.nombre}
      >
        <p className="text-sm text-muted-foreground">
          El cliente y sus <span className="font-medium text-foreground">{cliente.bicicletas.length}</span>{" "}
          bicicleta(s) salen del directorio. No se borra nada: su historial de fichas y ventas se
          conserva, y puedes restaurarlo desde la pestaña «Archivados» del listado.
        </p>

        <div className="mt-4">
          <FormError
            message={
              desactivar.isError ? apiErrorMessage(desactivar.error, "No se pudo archivar") : null
            }
          />
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setConfirmOpen(false)}>
            Cancelar
          </Button>
          <Button
            variant="danger"
            disabled={desactivar.isPending}
            onClick={() => desactivar.mutate()}
          >
            Archivar
          </Button>
        </div>
      </Modal>
    </div>
  )
}
