import { useEffect, useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Check, Copy, Loader2, MessageCircle } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { Button, Field, FormError, Input, Textarea } from "@/components/ui/Form"
import { Modal } from "@/components/ui/Modal"
import type { CompartirComprobante } from "./types"

export function CompartirComprobanteModal({
  open,
  onClose,
  comprobanteId,
  titulo,
}: {
  open: boolean
  onClose: () => void
  comprobanteId: string | null
  /** Serie-número del comprobante, para el encabezado del modal. */
  titulo: string
}) {
  const [telefono, setTelefono] = useState("")
  const [copiado, setCopiado] = useState(false)

  const generar = useMutation({
    mutationFn: async () =>
      (
        await api.post<CompartirComprobante>(
          `${API_PREFIX}/facturacion/documentos/${comprobanteId}/whatsapp`,
          null,
          { params: { telefono: telefono.trim() || undefined } },
        )
      ).data,
  })

  // Al abrir para otro documento se limpia el estado anterior: el modal se
  // reutiliza desde cada fila del listado.
  useEffect(() => {
    if (open) {
      setTelefono("")
      setCopiado(false)
      generar.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, comprobanteId])

  const datos = generar.data

  const copiar = async () => {
    if (!datos) return
    await navigator.clipboard.writeText(datos.url_pdf)
    setCopiado(true)
    setTimeout(() => setCopiado(false), 2000)
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Enviar comprobante al cliente"
      description={titulo}
    >
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
            <Textarea rows={9} readOnly value={datos.mensaje} className="text-xs" />
          </Field>

          <div className="mt-3 flex items-center gap-2">
            <Input readOnly value={datos.url_pdf} className="text-xs" />
            <Button variant="secondary" onClick={copiar} className="shrink-0">
              {copiado ? (
                <Check className="h-4 w-4 text-state-success" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
              {copiado ? "Copiado" : "Copiar"}
            </Button>
          </div>

          <p className="mt-2 text-xs text-muted-foreground">
            Se abre WhatsApp con el mensaje listo; el cliente no necesita cuenta para abrir el PDF.
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
