import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle,
  CheckCircle2,
  Eye,
  EyeOff,
  Loader2,
  ShieldCheck,
  Trash2,
  Upload,
} from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { usePermission } from "@/lib/auth"
import { Badge } from "@/components/ui/Badge"
import { Button, Field, FormError, Input, Select } from "@/components/ui/Form"
import { Modal } from "@/components/ui/Modal"
import { PageHeader } from "@/components/ui/PageHeader"
import { SkeletonCard } from "@/components/ui/skeleton"
import { fmtFecha } from "@/features/clientes/types"

type Configuracion = {
  tiene_certificado: boolean
  certificado_nombre: string | null
  certificado_vence: string | null
  certificado_emitido_a: string | null
  certificado_cargado_at: string | null
  dias_para_vencer: number | null
  sol_usuario: string | null
  tiene_sol_clave: boolean
  produccion: boolean
  ruc: string
  razon_social: string
  nombre_comercial: string
  ubigeo: string
  direccion: string
  departamento: string
  provincia: string
  distrito: string
  serie_factura: string
  serie_boleta: string
  serie_nc_factura: string
  serie_nc_boleta: string
  declaracion_automatica: boolean
  lista_para_emitir: boolean
  actualizado_por: string | null
  updated_at: string | null
}

type DocumentoDePrueba = { serie: string; tipo: string; cantidad: number; total: string }
type Limpieza = {
  documentos: DocumentoDePrueba[]
  total_documentos: number
  lotes: number
  ventas_afectadas: number
  comprobantes_en_produccion: number
}

/** Se avisa con un mes: renovar un certificado no es inmediato. */
const DIAS_AVISO = 30

export default function ConfiguracionPage() {
  const qc = useQueryClient()
  const canEditar = usePermission("configuracion.editar")

  const { data, isLoading } = useQuery({
    queryKey: ["configuracion", "sunat"],
    queryFn: async () =>
      (await api.get<Configuracion>(`${API_PREFIX}/configuracion/sunat`)).data,
  })

  const [form, setForm] = useState<Partial<Configuracion>>({})
  const [solUsuario, setSolUsuario] = useState("")
  const [solClave, setSolClave] = useState("")
  const [verClave, setVerClave] = useState(false)
  const [verClaveCert, setVerClaveCert] = useState(false)
  const [limpiarOpen, setLimpiarOpen] = useState(false)
  const [archivo, setArchivo] = useState<File | null>(null)
  const [claveCert, setClaveCert] = useState("")

  useEffect(() => {
    if (data) setForm(data)
  }, [data])

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ["configuracion"] })
    qc.invalidateQueries({ queryKey: ["facturacion"] })
  }

  const guardar = useMutation({
    mutationFn: async () => {
      await api.put(`${API_PREFIX}/configuracion/sunat`, {
        ...form,
        // Vacío significa "no lo cambies": el formulario nunca trae los
        // valores actuales, porque no se devuelven en claro.
        sol_usuario: solUsuario || undefined,
        sol_clave: solClave || undefined,
      })
    },
    onSuccess: () => {
      invalidar()
      // Los secretos no se quedan en memoria más de lo necesario.
      setSolUsuario("")
      setSolClave("")
      setVerClave(false)
    },
  })

  const subir = useMutation({
    mutationFn: async () => {
      const fd = new FormData()
      fd.append("archivo", archivo as File)
      fd.append("clave", claveCert)
      await api.post(`${API_PREFIX}/configuracion/sunat/certificado`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      })
    },
    onSuccess: () => {
      invalidar()
      setArchivo(null)
      setClaveCert("")
      setVerClaveCert(false)
    },
  })

  const limpieza = useQuery({
    queryKey: ["configuracion", "documentos-prueba"],
    queryFn: async () =>
      (await api.get<Limpieza>(`${API_PREFIX}/configuracion/sunat/documentos-prueba`)).data,
  })

  const limpiar = useMutation({
    mutationFn: async () => {
      await api.delete(`${API_PREFIX}/configuracion/sunat/documentos-prueba`, {
        params: { confirmar: true },
      })
    },
    onSuccess: () => {
      invalidar()
      setLimpiarOpen(false)
    },
  })

  if (isLoading || !data) return <SkeletonCard className="h-80" />

  const dias = data.dias_para_vencer
  const vencido = dias !== null && dias < 0
  const porVencer = dias !== null && dias >= 0 && dias <= DIAS_AVISO
  // Un certificado caducado no firma: el aviso no puede decir que todo va bien
  // sólo porque los campos estén rellenos.
  const puedeEmitir = data.lista_para_emitir && !vencido
  const campo = (k: keyof Configuracion) => (form[k] as string) ?? ""
  const set = (k: keyof Configuracion, v: string | boolean) =>
    setForm((f) => ({ ...f, [k]: v }))

  return (
    <div>
      <PageHeader
        title="Configuración de facturación"
        description="Certificado digital, credenciales SOL y datos del emisor."
      />

      {/* ---------- Estado general ---------- */}
      <div
        className={
          "mb-4 flex items-start gap-2 rounded-md border px-4 py-3 text-sm " +
          (puedeEmitir
            ? "border-state-success/30 bg-state-success/10 text-state-success"
            : vencido
              ? "border-state-danger/30 bg-state-danger/10 text-state-danger"
              : "border-state-warning/40 bg-state-warning/10 text-state-warning")
        }
      >
        {puedeEmitir ? (
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
        ) : (
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        )}
        <div>
          <p className="font-medium">
            {vencido
              ? "Certificado digital vencido"
              : puedeEmitir
                ? data.produccion
                  ? "Emitiendo a SUNAT en producción"
                  : "Emitiendo al ambiente de pruebas de SUNAT"
                : "Modo simulación"}
          </p>
          <p className="text-xs">
            {vencido
              ? "La firma caducó. Carga un certificado vigente para poder emitir."
              : puedeEmitir
                ? data.produccion
                  ? "Los comprobantes tienen validez tributaria."
                  : "Los comprobantes se envían a SUNAT pero NO tienen validez: es el ambiente de pruebas."
                : "Falta el certificado o las credenciales SOL. Los comprobantes se generan pero no se envían ni valen."}
          </p>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* ---------- Certificado ---------- */}
        <div className="rounded-lg border border-border bg-card p-5">
          <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <ShieldCheck className="h-3.5 w-3.5" />
            Certificado digital
          </h2>

          {data.tiene_certificado ? (
            <dl className="mt-3 space-y-1.5 text-sm">
              <div className="flex justify-between gap-3">
                <dt className="text-muted-foreground">Archivo</dt>
                <dd className="truncate">{data.certificado_nombre}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted-foreground">Vence</dt>
                <dd className="flex items-center gap-2">
                  {data.certificado_vence ? fmtFecha(data.certificado_vence) : "—"}
                  {vencido && <Badge tone="danger">Vencido</Badge>}
                  {porVencer && <Badge tone="warning">{dias} días</Badge>}
                </dd>
              </div>
              {data.certificado_emitido_a && (
                <div className="pt-1">
                  <dt className="text-xs text-muted-foreground">Emitido a</dt>
                  <dd className="break-all text-xs">{data.certificado_emitido_a}</dd>
                </div>
              )}
            </dl>
          ) : (
            <p className="mt-3 text-sm text-muted-foreground">
              No hay certificado cargado. Sin él no se puede firmar ningún comprobante.
            </p>
          )}

          {vencido && (
            <div className="mt-3 rounded-md border border-state-danger/30 bg-state-danger/10 px-3 py-2 text-xs text-state-danger">
              El certificado venció. Hasta que se cargue uno vigente no se puede emitir.
            </div>
          )}

          {canEditar && (
            <div className="mt-4 border-t border-border pt-4">
              <Field
                label={data.tiene_certificado ? "Reemplazar certificado" : "Certificado (.pfx o .p12)"}
                hint="El archivo se guarda cifrado. Nunca se descarga ni se muestra."
              >
                <input
                  type="file"
                  accept=".pfx,.p12"
                  onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
                  className="w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-secondary file:px-3 file:py-1.5 file:text-sm"
                />
              </Field>
              <Field label="Clave del certificado" className="mt-3">
                <div className="relative">
                  <Input
                    type={verClaveCert ? "text" : "password"}
                    value={claveCert}
                    onChange={(e) => setClaveCert(e.target.value)}
                    placeholder="••••••••"
                    autoComplete="new-password"
                    spellCheck={false}
                    className="pr-9"
                  />
                  <button
                    type="button"
                    onClick={() => setVerClaveCert((v) => !v)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    title={verClaveCert ? "Ocultar" : "Mostrar mientras escribes"}
                    tabIndex={-1}
                  >
                    {verClaveCert ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </Field>
              <div className="mt-3">
                <FormError
                  message={
                    subir.isError
                      ? apiErrorMessage(subir.error, "No se pudo cargar el certificado")
                      : null
                  }
                />
              </div>
              <Button
                className="mt-3 w-full"
                disabled={!archivo || !claveCert || subir.isPending}
                onClick={() => subir.mutate()}
              >
                {subir.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Upload className="h-4 w-4" />
                )}
                Cargar certificado
              </Button>
            </div>
          )}
        </div>

        {/* ---------- Credenciales SOL ---------- */}
        <div className="rounded-lg border border-border bg-card p-5">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Credenciales SOL
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Se guardan cifradas y no se vuelven a mostrar. Con un usuario
            <strong> secundario</strong> podrías revocar este acceso desde SUNAT sin tocar tu
            clave principal.
          </p>

          <Field
            label="Usuario SOL"
            className="mt-3"
            hint={
              data.sol_usuario
                ? `Guardado: ${data.sol_usuario}. Escribe uno nuevo sólo si quieres cambiarlo.`
                : "Sin usuario no se puede enviar nada a SUNAT."
            }
          >
            <Input
              value={solUsuario}
              onChange={(e) => setSolUsuario(e.target.value)}
              disabled={!canEditar}
              placeholder={data.sol_usuario ? "(sin cambios)" : "MIUSUARIO"}
              autoComplete="off"
              spellCheck={false}
            />
          </Field>
          <Field
            label="Clave SOL"
            className="mt-3"
            hint={
              data.tiene_sol_clave
                ? "Ya hay una clave guardada. Escribe una nueva sólo si quieres cambiarla."
                : "Sin clave no se puede enviar nada a SUNAT."
            }
          >
            <div className="relative">
              <Input
                type={verClave ? "text" : "password"}
                value={solClave}
                onChange={(e) => setSolClave(e.target.value)}
                disabled={!canEditar}
                placeholder={data.tiene_sol_clave ? "••••••••  (sin cambios)" : "Clave SOL"}
                autoComplete="new-password"
                spellCheck={false}
                className="pr-9"
              />
              {/* Revelar lo tecleado evita guardar una clave mal escrita, que
                  sólo se descubriría al fallar la siguiente emisión. */}
              <button
                type="button"
                onClick={() => setVerClave((v) => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                title={verClave ? "Ocultar" : "Mostrar mientras escribes"}
                tabIndex={-1}
              >
                {verClave ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </Field>

          <Field label="Ambiente" className="mt-3">
            <Select
              value={form.produccion ? "1" : "0"}
              onChange={(e) => set("produccion", e.target.value === "1")}
              disabled={!canEditar}
            >
              <option value="0">Pruebas — los documentos no tienen validez</option>
              <option value="1">Producción — validez tributaria real</option>
            </Select>
          </Field>

          <Field
            label="Declaración automática"
            className="mt-3"
            hint="Manda el resumen de boletas del día anterior cada mañana, sin que nadie lo pulse."
          >
            <Select
              value={form.declaracion_automatica ? "1" : "0"}
              onChange={(e) => set("declaracion_automatica", e.target.value === "1")}
              disabled={!canEditar}
            >
              <option value="0">Manual — se declara desde Documentos</option>
              <option value="1">Automática — cada mañana</option>
            </Select>
          </Field>
        </div>
      </div>

      {/* ---------- Emisor y series ---------- */}
      <div className="mt-4 rounded-lg border border-border bg-card p-5">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Emisor y series
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Estos datos viajan dentro del XML y deben coincidir con el padrón de SUNAT. Las
          series las autoriza SUNAT: emitir con una que no esté habilitada se rechaza.
        </p>

        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="RUC">
            <Input value={campo("ruc")} onChange={(e) => set("ruc", e.target.value)} disabled={!canEditar} />
          </Field>
          <Field label="Razón social" className="sm:col-span-2">
            <Input value={campo("razon_social")} onChange={(e) => set("razon_social", e.target.value)} disabled={!canEditar} />
          </Field>
          <Field label="Nombre comercial">
            <Input value={campo("nombre_comercial")} onChange={(e) => set("nombre_comercial", e.target.value)} disabled={!canEditar} />
          </Field>
          <Field label="Ubigeo">
            <Input value={campo("ubigeo")} onChange={(e) => set("ubigeo", e.target.value)} disabled={!canEditar} placeholder="120101" />
          </Field>
          <Field label="Dirección" className="sm:col-span-2 lg:col-span-3">
            <Input value={campo("direccion")} onChange={(e) => set("direccion", e.target.value)} disabled={!canEditar} />
          </Field>
          <Field label="Departamento">
            <Input value={campo("departamento")} onChange={(e) => set("departamento", e.target.value)} disabled={!canEditar} />
          </Field>
          <Field label="Provincia">
            <Input value={campo("provincia")} onChange={(e) => set("provincia", e.target.value)} disabled={!canEditar} />
          </Field>
          <Field label="Distrito">
            <Input value={campo("distrito")} onChange={(e) => set("distrito", e.target.value)} disabled={!canEditar} />
          </Field>
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Serie de facturas">
            <Input value={campo("serie_factura")} onChange={(e) => set("serie_factura", e.target.value.toUpperCase())} disabled={!canEditar} maxLength={4} />
          </Field>
          <Field label="Serie de boletas">
            <Input value={campo("serie_boleta")} onChange={(e) => set("serie_boleta", e.target.value.toUpperCase())} disabled={!canEditar} maxLength={4} />
          </Field>
          <Field label="Serie NC de facturas">
            <Input value={campo("serie_nc_factura")} onChange={(e) => set("serie_nc_factura", e.target.value.toUpperCase())} disabled={!canEditar} maxLength={4} />
          </Field>
          <Field label="Serie NC de boletas">
            <Input value={campo("serie_nc_boleta")} onChange={(e) => set("serie_nc_boleta", e.target.value.toUpperCase())} disabled={!canEditar} maxLength={4} />
          </Field>
        </div>

        <div className="mt-4">
          <FormError
            message={guardar.isError ? apiErrorMessage(guardar.error, "No se pudo guardar") : null}
          />
        </div>

        {canEditar && (
          <div className="mt-4 flex items-center justify-between gap-3 border-t border-border pt-4">
            <p className="text-xs text-muted-foreground">
              {data.actualizado_por
                ? `Última modificación por ${data.actualizado_por}.`
                : "Sin modificaciones registradas."}
            </p>
            <Button disabled={guardar.isPending} onClick={() => guardar.mutate()}>
              {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Guardar cambios
            </Button>
          </div>
        )}
      </div>

      {/* ---------- Documentos de prueba ---------- */}
      {canEditar && (limpieza.data?.total_documentos ?? 0) > 0 && (
        <div className="mt-4 rounded-lg border border-state-warning/40 bg-state-warning/5 p-5">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Documentos de prueba
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Hay <strong>{limpieza.data?.total_documentos}</strong> comprobante(s) emitidos
            contra el ambiente de pruebas. Conviene retirarlos antes de emitir en serio: el
            registro de ventas del contador filtra por fecha, no por ambiente, y se
            declararían como si fueran válidos.
          </p>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap gap-1.5">
              {limpieza.data?.documentos.map((d) => (
                <Badge key={`${d.serie}-${d.tipo}`} tone="neutral">
                  {d.serie} · {d.cantidad}
                </Badge>
              ))}
              {(limpieza.data?.lotes ?? 0) > 0 && (
                <Badge tone="neutral">{limpieza.data?.lotes} resumen(es)</Badge>
              )}
            </div>
            <Button variant="danger" onClick={() => setLimpiarOpen(true)}>
              <Trash2 className="h-4 w-4" />
              Limpiar documentos de prueba
            </Button>
          </div>

          {(limpieza.data?.comprobantes_en_produccion ?? 0) > 0 && (
            <p className="mt-3 text-xs text-muted-foreground">
              Los <strong>{limpieza.data?.comprobantes_en_produccion}</strong> comprobante(s)
              emitidos en producción no se tocan.
            </p>
          )}
        </div>
      )}

      <Modal
        open={limpiarOpen}
        onClose={() => setLimpiarOpen(false)}
        title="Limpiar documentos de prueba"
        description={`Se retirarán ${limpieza.data?.total_documentos ?? 0} comprobante(s)`}
      >
        <p className="text-sm text-muted-foreground">
          Se borran los comprobantes emitidos contra el ambiente de pruebas y los resúmenes
          que los declararon. <strong className="text-foreground">No se puede deshacer.</strong>
        </p>

        <ul className="mt-3 space-y-1.5 rounded-md border border-border bg-muted/40 px-3 py-2.5 text-sm">
          <li>
            Los comprobantes emitidos en <strong>producción no se tocan</strong>
            {(limpieza.data?.comprobantes_en_produccion ?? 0) > 0
              ? ` (${limpieza.data?.comprobantes_en_produccion} a salvo).`
              : "."}
          </li>
          <li>
            Las <strong>ventas no se borran</strong>
            {(limpieza.data?.ventas_afectadas ?? 0) > 0
              ? `: ${limpieza.data?.ventas_afectadas} volverán a quedar pendientes de facturar.`
              : "."}
          </li>
          <li>El correlativo vuelve a empezar en 1 en las series que queden vacías.</li>
        </ul>

        <div className="mt-4">
          <FormError
            message={limpiar.isError ? apiErrorMessage(limpiar.error, "No se pudo limpiar") : null}
          />
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setLimpiarOpen(false)}>
            Cancelar
          </Button>
          <Button variant="danger" disabled={limpiar.isPending} onClick={() => limpiar.mutate()}>
            {limpiar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Borrar definitivamente
          </Button>
        </div>
      </Modal>
    </div>
  )
}
