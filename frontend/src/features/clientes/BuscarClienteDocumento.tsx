import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Check, Loader2, Search, UserPlus, X } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { Button, Input, Select } from "@/components/ui/Form"
import type { Cliente, Page, TipoDocumento } from "./types"

const LARGO: Record<string, number> = { DNI: 8, RUC: 11 }

/**
 * Busca un cliente por su documento para el mostrador.
 *
 * Flujo pensado para el momento del cobro: se tipea el documento y
 *  1. se busca entre los clientes YA registrados (lo más común: es recurrente);
 *  2. si no está, se consulta RENIEC/SUNAT y se ofrece registrarlo en un clic.
 *
 * Así el cajero nunca tiene que salir del punto de venta a crear el cliente.
 */
export function BuscarClienteDocumento({
  clienteId,
  onSeleccionar,
}: {
  clienteId: string
  onSeleccionar: (cliente: Cliente | null) => void
}) {
  const qc = useQueryClient()
  const [tipo, setTipo] = useState<TipoDocumento>("DNI")
  const [numero, setNumero] = useState("")
  const [encontradoPadron, setEncontradoPadron] = useState<{
    nombre: string
    direccion: string | null
  } | null>(null)
  const [seleccionado, setSeleccionado] = useState<Cliente | null>(null)

  // Si el padre limpia el cliente (p. ej. tras cobrar), se resetea el bloque.
  useEffect(() => {
    if (!clienteId && seleccionado) {
      setSeleccionado(null)
      setNumero("")
      setEncontradoPadron(null)
    }
  }, [clienteId, seleccionado])

  const consultaDisponible = useQuery({
    queryKey: ["clientes", "consulta-disponible"],
    queryFn: async () =>
      (
        await api.get<{ disponible: boolean }>(
          `${API_PREFIX}/clientes/consulta-documento/disponible`,
        )
      ).data.disponible,
    staleTime: 5 * 60_000,
  })

  const largoOk = numero.length === (LARGO[tipo] ?? 0)

  const buscar = useMutation({
    mutationFn: async () => {
      // 1) ¿Ya está registrado?
      const local = await api.get<Page<Cliente>>(`${API_PREFIX}/clientes`, {
        params: { search: numero, is_active: true, page_size: 5 },
      })
      const exacto = local.data.items.find((c) => c.numero_documento === numero)
      if (exacto) return { tipo: "local" as const, cliente: exacto }

      // 2) Si no, consultar el padrón (si está configurado).
      if (!consultaDisponible.data) {
        return { tipo: "no_encontrado" as const }
      }
      const { data } = await api.get<{ nombre: string; direccion: string | null }>(
        `${API_PREFIX}/clientes/consulta-documento`,
        { params: { tipo, numero } },
      )
      return { tipo: "padron" as const, datos: data }
    },
    onSuccess: (r) => {
      if (r.tipo === "local") {
        setSeleccionado(r.cliente)
        setEncontradoPadron(null)
        onSeleccionar(r.cliente)
      } else if (r.tipo === "padron") {
        setEncontradoPadron(r.datos)
      }
    },
  })

  const registrar = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<Cliente>(`${API_PREFIX}/clientes`, {
        nombre: encontradoPadron!.nombre,
        tipo_documento: tipo,
        numero_documento: numero,
        direccion: encontradoPadron!.direccion,
      })
      return data
    },
    onSuccess: (cliente) => {
      qc.invalidateQueries({ queryKey: ["clientes"] })
      setSeleccionado(cliente)
      setEncontradoPadron(null)
      onSeleccionar(cliente)
    },
  })

  const limpiar = () => {
    setSeleccionado(null)
    setEncontradoPadron(null)
    setNumero("")
    onSeleccionar(null)
  }

  // Cliente ya elegido: se muestra como "chip" con opción de quitarlo.
  if (seleccionado) {
    return (
      <div className="rounded-lg border border-state-success/30 bg-state-success/5 px-3 py-2.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="flex items-center gap-1.5 text-sm font-medium">
              <Check className="h-3.5 w-3.5 shrink-0 text-state-success" />
              <span className="truncate">{seleccionado.nombre}</span>
            </p>
            <p className="tabular mt-0.5 text-xs text-muted-foreground">
              {seleccionado.tipo_documento} {seleccionado.numero_documento}
            </p>
          </div>
          <button
            type="button"
            onClick={limpiar}
            className="shrink-0 rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            aria-label="Quitar cliente"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex gap-2">
        <Select
          value={tipo}
          onChange={(e) => {
            setTipo(e.target.value as TipoDocumento)
            setEncontradoPadron(null)
          }}
          className="w-24 shrink-0"
        >
          <option value="DNI">DNI</option>
          <option value="RUC">RUC</option>
        </Select>
        <Input
          value={numero}
          onChange={(e) => {
            setNumero(e.target.value.replace(/\D/g, ""))
            setEncontradoPadron(null)
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && largoOk) {
              e.preventDefault()
              buscar.mutate()
            }
          }}
          placeholder={tipo === "RUC" ? "20601234567" : "45678912"}
          inputMode="numeric"
        />
        <Button
          type="button"
          variant="secondary"
          className="shrink-0"
          disabled={!largoOk || buscar.isPending}
          onClick={() => buscar.mutate()}
        >
          {buscar.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Search className="h-4 w-4" />
          )}
        </Button>
      </div>

      {/* Encontrado en el padrón: aún no existe como cliente. */}
      {encontradoPadron && (
        <div className="mt-2 rounded-lg border border-border bg-muted/40 px-3 py-2.5">
          <p className="text-sm font-medium">{encontradoPadron.nombre}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Encontrado en {tipo === "RUC" ? "SUNAT" : "RENIEC"} · aún no es cliente
          </p>
          <Button
            type="button"
            className="mt-2 w-full"
            disabled={registrar.isPending}
            onClick={() => registrar.mutate()}
          >
            {registrar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <UserPlus className="h-4 w-4" />
            )}
            Registrar y usar
          </Button>
        </div>
      )}

      {buscar.isSuccess && buscar.data?.tipo === "no_encontrado" && (
        <p className="mt-2 text-xs text-muted-foreground">
          No está registrado. La consulta a RENIEC/SUNAT no está configurada.
        </p>
      )}

      {(buscar.isError || registrar.isError) && (
        <p className="mt-2 text-xs text-state-danger">
          {apiErrorMessage(
            buscar.error ?? registrar.error,
            "No se pudo buscar el cliente",
          )}
        </p>
      )}
    </div>
  )
}
