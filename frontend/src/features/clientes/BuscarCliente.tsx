import { useEffect, useId, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Loader2, Search, UserPlus } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import type { Cliente, Page, TipoDocumento } from "./types"

/** Los dos únicos documentos que el padrón sabe consultar. */
type DocConsultable = Extract<TipoDocumento, "DNI" | "RUC">

const tipoDeDocumento = (texto: string): DocConsultable | null => {
  if (!/^\d+$/.test(texto)) return null
  if (texto.length === 8) return "DNI"
  if (texto.length === 11) return "RUC"
  return null
}

const PADRON: Record<DocConsultable, string> = { DNI: "RENIEC", RUC: "SUNAT" }

/**
 * Buscador de clientes del mostrador, con alta desde el padrón.
 *
 * Un solo campo cubre los dos casos del día a día: el cliente recurrente, que
 * aparece entre las sugerencias por nombre o documento, y el que viene por
 * primera vez, cuyo DNI o RUC no da resultados locales pero sí en
 * RENIEC/SUNAT — y entonces se registra y se usa en un clic, sin abrir el
 * formulario de alta ni salir de la venta.
 */
export function BuscarCliente({
  onSeleccionar,
  placeholder = "Buscar cliente por nombre o documento",
}: {
  onSeleccionar: (cliente: Cliente) => void
  placeholder?: string
}) {
  const qc = useQueryClient()
  const listaId = useId()
  const [texto, setTexto] = useState("")
  const [busqueda, setBusqueda] = useState("")
  const [abierto, setAbierto] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setBusqueda(texto.trim()), 300)
    return () => clearTimeout(t)
  }, [texto])

  // El desplegable plano no escala cuando el directorio crece, así que se
  // consulta al servidor con debounce.
  const clientesQ = useQuery({
    queryKey: ["clientes", "buscar", busqueda],
    queryFn: async () =>
      (
        await api.get<Page<Cliente>>(`${API_PREFIX}/clientes`, {
          params: { search: busqueda, is_active: true, page_size: 8 },
        })
      ).data,
    enabled: busqueda.length >= 2,
  })

  const sugerencias = busqueda.length >= 2 ? (clientesQ.data?.items ?? []) : []

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

  const tipo = tipoDeDocumento(busqueda)
  // Sólo se molesta al padrón cuando el documento no está ya registrado: lo
  // habitual es que el cliente sea recurrente y la consulta externa sobre.
  const yaRegistrado = sugerencias.some((c) => c.numero_documento === busqueda)
  const consultarPadron =
    tipo !== null && !yaRegistrado && clientesQ.isSuccess && consultaDisponible.data === true

  const padronQ = useQuery({
    queryKey: ["clientes", "padron", busqueda],
    queryFn: async () =>
      (
        await api.get<{ nombre: string; direccion: string | null }>(
          `${API_PREFIX}/clientes/consulta-documento`,
          { params: { tipo, numero: busqueda } },
        )
      ).data,
    enabled: consultarPadron,
    // Un documento que no existe devuelve error: reintentarlo sólo demora la
    // respuesta al mostrador.
    retry: false,
  })

  const elegir = (c: Cliente) => {
    onSeleccionar(c)
    setTexto("")
    setBusqueda("")
    setAbierto(false)
  }

  const registrar = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<Cliente>(`${API_PREFIX}/clientes`, {
        nombre: padronQ.data!.nombre,
        tipo_documento: tipo,
        numero_documento: busqueda,
        direccion: padronQ.data?.direccion ?? null,
      })
      return data
    },
    onSuccess: (cliente) => {
      qc.invalidateQueries({ queryKey: ["clientes"] })
      elegir(cliente)
    },
  })

  const mostrar = abierto && busqueda.length >= 2
  const enPadron = consultarPadron ? padronQ.data : undefined

  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <input
        value={texto}
        onChange={(e) => {
          setTexto(e.target.value)
          setAbierto(true)
        }}
        onFocus={() => setAbierto(true)}
        // El clic sobre una sugerencia se resuelve en onMouseDown, así que al
        // llegar el blur el cliente ya quedó elegido. Registrar desde el padrón
        // tarda, y cerrar la lista a media alta dejaría al cajero sin saber
        // qué pasó: mientras se registra, el desplegable se mantiene.
        onBlur={() => {
          if (!registrar.isPending) setAbierto(false)
        }}
        placeholder={placeholder}
        role="combobox"
        aria-expanded={mostrar}
        aria-controls={listaId}
        aria-autocomplete="list"
        className="w-full rounded-md border border-border bg-background py-2 pl-8 pr-3 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
      />

      {mostrar && (
        <ul
          id={listaId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-md border border-border bg-card shadow-lg"
        >
          {sugerencias.map((c) => (
            <li key={c.id} role="option" aria-selected={false}>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault()
                  elegir(c)
                }}
                className="flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left text-sm hover:bg-accent"
              >
                <span className="block max-w-full truncate font-medium">{c.nombre}</span>
                <span className="tabular block max-w-full truncate text-xs text-muted-foreground">
                  {c.tipo_documento} {c.numero_documento}
                  {c.telefono ? ` · ${c.telefono}` : ""}
                </span>
              </button>
            </li>
          ))}

          {/* Encontrado en el padrón: todavía no es cliente, se crea al vuelo. */}
          {enPadron && (
            <li className="border-t border-border bg-muted/30 p-2.5">
              <p className="text-sm font-medium">{enPadron.nombre}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Encontrado en {PADRON[tipo!]} · aún no es cliente
              </p>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault()
                  registrar.mutate()
                }}
                disabled={registrar.isPending}
                className="mt-2 inline-flex w-full items-center justify-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-60"
              >
                {registrar.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <UserPlus className="h-4 w-4" />
                )}
                Registrar y usar
              </button>
              {registrar.isError && (
                <p className="mt-1.5 text-xs text-state-danger">
                  {apiErrorMessage(registrar.error, "No se pudo registrar el cliente")}
                </p>
              )}
            </li>
          )}

          {sugerencias.length === 0 && !enPadron && (
            <li className="px-3 py-3 text-sm text-muted-foreground">
              {clientesQ.isFetching || padronQ.isFetching
                ? "Buscando…"
                : tipo && consultaDisponible.data === false
                  ? `Ningún cliente coincide con “${busqueda}”. La consulta a RENIEC/SUNAT no está configurada.`
                  : `Ningún cliente coincide con “${busqueda}”`}
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
