import { Archive, Loader2, Trash2 } from "lucide-react"

import { Button, FormError } from "./Form"
import { Modal } from "./Modal"

/**
 * Diálogo de borrado definitivo, compartido por inventario, clientes y
 * bicicletas.
 *
 * Los tres módulos siguen la misma regla: archivar es la salida normal y el
 * borrado real sólo procede si no hay documentos que citen al registro. Por eso
 * el diálogo ofrece "Mejor archivar" en el mismo sitio donde el backend suele
 * responder 409: el usuario resuelve sin volver a la tabla.
 */
export function ConfirmarEliminar({
  open,
  onClose,
  titulo,
  subtitulo,
  children,
  error,
  cargando,
  onEliminar,
  onArchivar,
}: {
  open: boolean
  onClose: () => void
  titulo: string
  subtitulo?: string
  /** Qué se lleva por delante el borrado, en palabras del módulo. */
  children: React.ReactNode
  error?: string | null
  cargando?: boolean
  onEliminar: () => void
  /** Ausente si el registro ya está archivado: no hay atajo que ofrecer. */
  onArchivar?: () => void
}) {
  return (
    <Modal open={open} onClose={onClose} title={titulo} description={subtitulo}>
      <div className="text-sm text-muted-foreground">{children}</div>

      <FormError message={error ?? null} />

      <div className="mt-4 flex flex-wrap justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancelar
        </Button>
        {onArchivar && (
          <Button variant="secondary" onClick={onArchivar}>
            <Archive className="h-4 w-4" />
            Mejor archivar
          </Button>
        )}
        <Button variant="danger" disabled={cargando} onClick={onEliminar}>
          {cargando ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Trash2 className="h-4 w-4" />
          )}
          Eliminar
        </Button>
      </div>
    </Modal>
  )
}
