import { useEffect, useRef, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, CheckCircle2, Download, FileSpreadsheet, Loader2, Upload } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { cn } from "@/lib/utils"
import { Button, FormError } from "@/components/ui/Form"
import { Modal } from "@/components/ui/Modal"
import type { ResultadoImportacion } from "./types"

export function ImportarModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [archivo, setArchivo] = useState<File | null>(null)
  const [resultado, setResultado] = useState<ResultadoImportacion | null>(null)
  const [aplicado, setAplicado] = useState(false)

  useEffect(() => {
    if (open) {
      setArchivo(null)
      setResultado(null)
      setAplicado(false)
    }
  }, [open])

  const importar = useMutation({
    mutationFn: async (modoPrueba: boolean) => {
      const fd = new FormData()
      fd.append("archivo", archivo!)
      const { data } = await api.post<ResultadoImportacion>(
        `${API_PREFIX}/inventario/importar`,
        fd,
        {
          params: { modo_prueba: modoPrueba },
          headers: { "Content-Type": "multipart/form-data" },
        },
      )
      return { data, modoPrueba }
    },
    onSuccess: ({ data, modoPrueba }) => {
      setResultado(data)
      if (!modoPrueba && data.errores === 0) {
        setAplicado(true)
        qc.invalidateQueries({ queryKey: ["inventario"] })
      }
    },
  })

  const descargarPlantilla = async () => {
    const res = await api.get(`${API_PREFIX}/inventario/plantilla-excel`, {
      responseType: "blob",
    })
    const url = URL.createObjectURL(res.data as Blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "plantilla-inventario.xlsx"
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 30_000)
  }

  const elegir = (f: File | null) => {
    setArchivo(f)
    setResultado(null)
    setAplicado(false)
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Importar productos desde Excel"
      description="Primero se valida sin escribir nada; tú confirmas después."
      className="max-w-3xl"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border bg-muted/40 px-3 py-2.5">
        <p className="text-xs text-muted-foreground">
          ¿No sabes qué columnas usar? Descarga la plantilla con el formato exacto.
        </p>
        <Button type="button" variant="secondary" onClick={descargarPlantilla}>
          <Download className="h-3.5 w-3.5" />
          Plantilla Excel
        </Button>
      </div>

      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault()
          elegir(e.dataTransfer.files?.[0] ?? null)
        }}
        onClick={() => inputRef.current?.click()}
        className="mt-4 cursor-pointer rounded-lg border-2 border-dashed border-border px-4 py-8 text-center transition hover:border-primary/50 hover:bg-accent/40"
      >
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx"
          className="hidden"
          onChange={(e) => elegir(e.target.files?.[0] ?? null)}
        />
        <FileSpreadsheet className="mx-auto h-8 w-8 text-muted-foreground" />
        {archivo ? (
          <p className="mt-2 text-sm font-medium">{archivo.name}</p>
        ) : (
          <>
            <p className="mt-2 text-sm">Arrastra tu archivo .xlsx o haz clic para elegirlo</p>
            <p className="mt-0.5 text-xs text-muted-foreground">Máximo 5 MB</p>
          </>
        )}
      </div>

      {resultado && (
        <div className="mt-4">
          <div className="grid grid-cols-4 gap-2 text-center">
            {[
              { label: "Filas", valor: resultado.total_filas, clase: "" },
              { label: "Nuevos", valor: resultado.creados, clase: "text-state-success" },
              { label: "Actualizados", valor: resultado.actualizados, clase: "text-state-info" },
              { label: "Errores", valor: resultado.errores, clase: "text-state-danger" },
            ].map((s) => (
              <div key={s.label} className="rounded-md border border-border py-2">
                <p className={cn("tabular text-lg font-semibold", s.clase)}>{s.valor}</p>
                <p className="text-xs text-muted-foreground">{s.label}</p>
              </div>
            ))}
          </div>

          {resultado.errores > 0 && (
            <div className="mt-3 flex items-start gap-2 rounded-md border border-state-danger/30 bg-state-danger/10 px-3 py-2.5 text-xs text-state-danger">
              <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" />
              <span>
                No se aplicó nada. La importación es todo o nada: corrige las filas marcadas en
                rojo y vuelve a subir el archivo.
              </span>
            </div>
          )}

          {aplicado && (
            <div className="mt-3 flex items-start gap-2 rounded-md border border-state-success/30 bg-state-success/10 px-3 py-2.5 text-xs text-state-success">
              <CheckCircle2 className="mt-px h-3.5 w-3.5 shrink-0" />
              <span>
                Importación aplicada. Los cambios de stock quedaron registrados en el kardex.
              </span>
            </div>
          )}

          <div className="mt-3 max-h-64 overflow-y-auto rounded-md border border-border">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-secondary">
                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <th className="px-3 py-2">Fila</th>
                  <th className="px-3 py-2">SKU</th>
                  <th className="px-3 py-2">Resultado</th>
                </tr>
              </thead>
              <tbody>
                {resultado.filas.map((f) => (
                  <tr
                    key={f.fila}
                    className={cn(
                      "border-t border-border",
                      f.accion === "error" && "bg-state-danger/5",
                    )}
                  >
                    <td className="tabular px-3 py-1.5 text-muted-foreground">{f.fila}</td>
                    <td className="px-3 py-1.5 font-medium">{f.sku || "—"}</td>
                    <td className="px-3 py-1.5">
                      {f.accion === "error" ? (
                        <span className="text-state-danger">{f.detalle}</span>
                      ) : (
                        <span className="capitalize text-muted-foreground">{f.accion}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="mt-4">
        <FormError
          message={
            importar.isError ? apiErrorMessage(importar.error, "No se pudo leer el archivo") : null
          }
        />
      </div>

      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          {aplicado ? "Cerrar" : "Cancelar"}
        </Button>

        {!aplicado && (
          <>
            <Button
              variant="secondary"
              disabled={!archivo || importar.isPending}
              onClick={() => importar.mutate(true)}
            >
              {importar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Validar
            </Button>
            <Button
              disabled={!archivo || importar.isPending || !resultado || resultado.errores > 0}
              onClick={() => importar.mutate(false)}
              title={
                !resultado
                  ? "Valida el archivo antes de importar"
                  : resultado.errores > 0
                    ? "Corrige los errores antes de importar"
                    : undefined
              }
            >
              <Upload className="h-4 w-4" />
              Importar de verdad
            </Button>
          </>
        )}
      </div>
    </Modal>
  )
}
