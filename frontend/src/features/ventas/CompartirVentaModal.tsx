import { useEffect, useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Check, Copy, Loader2, MessageCircle } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { Button, Field, FormError, Input, Textarea } from "@/components/ui/Form"
import { Modal } from "@/components/ui/Modal"
import type { CompartirVenta } from "./types"

export function CompartirVentaModal({
  open,
  onClose,
  ventaId,
  titulo,
  telefonoCliente,
}: {
  open: boolean
  onClose: () => void
  ventaId: string | null
  /** N° del documento, para el encabezado del modal. */
  titulo: string
  telefonoCliente?: string | null
}) {
  const [telefono, setTelefono] = useState("")
  const [copiado, setCopiado] = useState<"enlace" | "mensaje" | null>(null)

  const generar = useMutation({
    mutationFn: async () =>
      (
        await api.post<CompartirVenta>(`${API_PREFIX}/ventas/${ventaId}/whatsapp`, null, {
          params: { telefono: telefono.trim() || undefined },
        })
      ).data,
  })

  // El modal se reutiliza desde cada fila del listado: al abrirlo para otro
  // documento hay que limpiar el enlace del anterior.
  useEffect(() => {
    if (open) {
      setTelefono(telefonoCliente ?? "")
      setCopiado(null)
      generar.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, ventaId, telefonoCliente])

  const datos = generar.data

  const copiar = async (que: "enlace" | "mensaje") => {
    if (!datos) return
    await navigator.clipboard.writeText(que === "enlace" ? datos.url_pdf : datos.mensaje)
    setCopiado(que)
    setTimeout(() => setCopiado(null), 2000)
  }

  return (
    <Modal open={open} onClose={onClose} title="Enviar documento al cliente" description={titulo}>
      <Field
        label="Teléfono de WhatsApp"
        hint="Vacío usa el teléfono registrado del cliente. Sin número, WhatsApp te dejará elegir el contacto."
      >
        <Input
          value={telefono}
          onChange={(e) => setTelefono(e.target.value)}
          placeholder="987654321"
        />
      </Field>

      {!datos ? (
        <>
          <div className="mt-4">
            <FormError
              message={
                generar.isError
                  ? apiErrorMessage(generar.error, "No se pudo generar el enlace")
                  : null
              }
            />
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="secondary" onClick={onClose}>
              Cancelar
            </Button>
            <Button disabled={generar.isPending} onClick={() => generar.mutate()}>
              {generar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Generar enlace
            </Button>
          </div>
        </>
      ) : (
        <>
          <Field label="Mensaje que se enviará" className="mt-4">
            <Textarea rows={11} readOnly value={datos.mensaje} className="text-xs" />
          </Field>

          {/* Abrir WhatsApp lleva el texto en el propio enlace, y su manejador
              puede estropear los emojis al decodificarlo. Copiado y pegado el
              mensaje llega intacto, así que se ofrecen las dos vías. */}
          <Button variant="secondary" onClick={() => copiar("mensaje")} className="mt-2 w-full">
            {copiado === "mensaje" ? (
              <Check className="h-4 w-4 text-state-success" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
            {copiado === "mensaje" ? "Mensaje copiado" : "Copiar mensaje"}
          </Button>

          <div className="mt-3 flex items-center gap-2">
            <Input readOnly value={datos.url_pdf} className="text-xs" />
            <Button variant="secondary" onClick={() => copiar("enlace")} className="shrink-0">
              {copiado === "enlace" ? (
                <Check className="h-4 w-4 text-state-success" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
              {copiado === "enlace" ? "Copiado" : "Copiar"}
            </Button>
          </div>

          <p className="mt-2 text-xs text-muted-foreground">
            Enlace corto y permanente al PDF. El cliente no necesita cuenta para abrirlo.
          </p>

          <div className="mt-4 flex justify-end gap-2">
            <Button variant="secondary" onClick={onClose}>
              Cerrar
            </Button>
            <a href={datos.whatsapp_url} target="_blank" rel="noreferrer">
              <Button className="bg-[#25D366] hover:bg-[#25D366]/90">
                <MessageCircle className="h-4 w-4" />
                Abrir WhatsApp
              </Button>
            </a>
          </div>
        </>
      )}
    </Modal>
  )
}
