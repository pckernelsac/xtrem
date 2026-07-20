import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import {
  AlertTriangle,
  Archive,
  ArchiveRestore,
  ArrowLeftRight,
  Boxes,
  ImageOff,
  PackageX,
  Pencil,
  Plus,
  Search,
  Trash2,
  Upload,
  Wallet,
} from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { usePermission } from "@/lib/auth"
import { Badge } from "@/components/ui/Badge"
import { Button, Select } from "@/components/ui/Form"
import { FilterTabs } from "@/components/ui/FilterTabs"
import { PageHeader } from "@/components/ui/PageHeader"
import { Paginacion } from "@/components/ui/Paginacion"
import { ConfirmarEliminar } from "@/components/ui/ConfirmarEliminar"
import { FormError } from "@/components/ui/Form"
import { SkeletonStatCard, SkeletonTable } from "@/components/ui/skeleton"
import type { Page } from "@/features/clientes/types"
import { ImportarModal } from "@/features/inventario/ImportarModal"
import { MovimientoModal } from "@/features/inventario/MovimientoModal"
import { ProductoFormModal } from "@/features/inventario/ProductoFormModal"
import {
  cantidad,
  soles,
  type Categoria,
  type Producto,
  type Resumen,
  type TipoItem,
} from "@/features/inventario/types"

const PAGE_SIZE = 25
type Tab = "todos" | "alertas" | "inactivos"
type FiltroTipo = "" | TipoItem

function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  alerta,
}: {
  label: string
  value: string | number
  hint: string
  icon: typeof Boxes
  alerta?: boolean
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 sm:p-5">
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </span>
        <span
          className={
            alerta
              ? "rounded-md bg-state-warning/12 p-1.5 text-state-warning"
              : "rounded-md bg-primary/10 p-1.5 text-primary"
          }
        >
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <p className="tabular mt-4 text-xl font-semibold sm:text-2xl">{value}</p>
      <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
    </div>
  )
}

export default function InventarioPage() {
  const canCreate = usePermission("inventario.crear")
  const canEdit = usePermission("inventario.editar")
  const canAjustar = usePermission("inventario.ajustar_stock")
  const canDelete = usePermission("inventario.eliminar")

  const [tab, setTab] = useState<Tab>("todos")
  const [tipo, setTipo] = useState<FiltroTipo>("")
  const [search, setSearch] = useState("")
  const [debounced, setDebounced] = useState("")
  const [categoriaId, setCategoriaId] = useState("")
  const [page, setPage] = useState(1)

  const [editando, setEditando] = useState<Producto | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [movProducto, setMovProducto] = useState<Producto | null>(null)
  const [importarOpen, setImportarOpen] = useState(false)

  // Archivar es reversible y se aplica directo; eliminar borra de verdad, así
  // que pasa por confirmación con el nombre del ítem a la vista.
  const [porEliminar, setPorEliminar] = useState<Producto | null>(null)
  const qc = useQueryClient()
  const refrescar = () => qc.invalidateQueries({ queryKey: ["inventario"] })

  const archivar = useMutation({
    mutationFn: async ({ id, activo }: { id: string; activo: boolean }) => {
      await api.patch(`${API_PREFIX}/inventario/productos/${id}`, { is_active: activo })
    },
    onSuccess: refrescar,
  })

  const eliminar = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`${API_PREFIX}/inventario/productos/${id}`)
    },
    onSuccess: () => {
      refrescar()
      setPorEliminar(null)
    },
  })

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search)
      setPage(1)
    }, 300)
    return () => clearTimeout(t)
  }, [search])

  const resumenQ = useQuery({
    queryKey: ["inventario", "resumen"],
    queryFn: async () => (await api.get<Resumen>(`${API_PREFIX}/inventario/resumen`)).data,
  })

  const categoriasQ = useQuery({
    queryKey: ["inventario", "categorias"],
    queryFn: async () =>
      (await api.get<Categoria[]>(`${API_PREFIX}/inventario/categorias`)).data,
  })

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["inventario", "productos", { tab, tipo, debounced, categoriaId, page }],
    queryFn: async () =>
      (
        await api.get<Page<Producto>>(`${API_PREFIX}/inventario/productos`, {
          params: {
            search: debounced || undefined,
            tipo: tipo || undefined,
            categoria_id: categoriaId || undefined,
            // "Todos" son los del catálogo vivo: lo archivado tiene su propia
            // pestaña, si no aparecería mezclado y con un conteo que no cuadra.
            is_active: tab !== "inactivos",
            solo_alertas: tab === "alertas" || undefined,
            page,
            page_size: PAGE_SIZE,
          },
        })
      ).data,
    placeholderData: (prev) => prev,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const resumen = resumenQ.data

  return (
    <div>
      <PageHeader
        title="Inventario"
        description="Productos y servicios, stock y kardex del almacén."
        actions={
          <div className="flex flex-wrap gap-2">
            <Link to="/inventario/kardex">
              <Button variant="secondary">
                <ArrowLeftRight className="h-4 w-4" />
                Kardex
              </Button>
            </Link>
            {canCreate && (
              <>
                <Button variant="secondary" onClick={() => setImportarOpen(true)}>
                  <Upload className="h-4 w-4" />
                  Importar Excel
                </Button>
                <Button
                  onClick={() => {
                    setEditando(null)
                    setFormOpen(true)
                  }}
                >
                  <Plus className="h-4 w-4" />
                  Nuevo producto
                </Button>
              </>
            )}
          </div>
        }
      />

      {/* Dos por fila ya en el móvil: apiladas, las cuatro tarjetas empujaban
          la tabla fuera de la primera pantalla. */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        {resumenQ.isLoading || !resumen ? (
          <>
            <SkeletonStatCard />
            <SkeletonStatCard />
            <SkeletonStatCard />
            <SkeletonStatCard />
          </>
        ) : (
          <>
            <StatCard
              label="Productos"
              value={resumen.productos_activos}
              hint={
                resumen.servicios_activos
                  ? `activos · y ${resumen.servicios_activos} servicio(s)`
                  : "activos en catálogo"
              }
              icon={Boxes}
            />
            <StatCard
              label="Bajo mínimo"
              value={resumen.bajo_minimo}
              hint="hay que reponer"
              icon={AlertTriangle}
              alerta={resumen.bajo_minimo > 0}
            />
            <StatCard
              label="Sin stock"
              value={resumen.sin_stock}
              hint="agotados"
              icon={PackageX}
              alerta={resumen.sin_stock > 0}
            />
            <StatCard
              label="Valor del stock"
              value={soles(resumen.valor_total)}
              hint="a precio de compra"
              icon={Wallet}
            />
          </>
        )}
      </div>

      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <FilterTabs<Tab>
          value={tab}
          onChange={(v) => {
            setTab(v)
            setPage(1)
          }}
          loading={resumenQ.isLoading}
          tabs={[
            {
              value: "todos",
              label: "Todos",
              count: (resumen?.productos_activos ?? 0) + (resumen?.servicios_activos ?? 0),
            },
            {
              value: "alertas",
              label: "Necesitan reposición",
              count: (resumen?.bajo_minimo ?? 0) + (resumen?.sin_stock ?? 0),
            },
            {
              value: "inactivos",
              label: "Archivados",
              count: resumen?.archivados ?? 0,
            },
          ]}
        />

        <div className="flex flex-wrap items-center gap-2">
          <Select
            value={tipo}
            onChange={(e) => {
              setTipo(e.target.value as FiltroTipo)
              setPage(1)
            }}
            className="w-44 py-1.5"
            aria-label="Tipo de ítem"
          >
            <option value="">Productos y servicios</option>
            <option value="PRODUCTO">Sólo productos</option>
            <option value="SERVICIO">Sólo servicios</option>
          </Select>

          <Select
            value={categoriaId}
            onChange={(e) => {
              setCategoriaId(e.target.value)
              setPage(1)
            }}
            className="w-44 py-1.5"
          >
            <option value="">Todas las categorías</option>
            {(categoriasQ.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.nombre} ({c.productos_count})
              </option>
            ))}
          </Select>

          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="SKU, nombre, marca..."
              className="w-64 rounded-md border border-border bg-background py-1.5 pl-8 pr-3 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
        </div>
      </div>

      {archivar.isError && (
        <div className="mb-3">
          <FormError message={apiErrorMessage(archivar.error, "No se pudo archivar")} />
        </div>
      )}

      {isLoading ? (
        <SkeletonTable
          rows={8}
          headers={["SKU", "Producto", "Categoría", "Stock", "Compra", "Venta", "Estado", ""]}
          columns={["w-24", "w-48", "w-24", "w-20", "w-20", "w-20", "w-24", "w-16"]}
        />
      ) : (
        <div className={isFetching ? "opacity-60 transition-opacity" : "transition-opacity"}>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-secondary">
                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-2.5">SKU</th>
                  <th className="px-4 py-2.5">Producto</th>
                  <th className="px-4 py-2.5">Categoría</th>
                  <th className="px-4 py-2.5 text-right">Stock</th>
                  <th className="px-4 py-2.5 text-right">Compra</th>
                  <th className="px-4 py-2.5 text-right">Venta</th>
                  <th className="px-4 py-2.5">Estado</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {items.map((p, i) => (
                  <tr
                    key={p.id}
                    className={
                      i % 2 === 1 ? "border-t border-border bg-muted/30" : "border-t border-border"
                    }
                  >
                    <td className="tabular px-4 py-2.5 font-medium">{p.sku}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-3">
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded border border-border bg-muted/40">
                          {p.foto_url ? (
                            <img
                              src={p.foto_url}
                              alt=""
                              loading="lazy"
                              className="h-full w-full object-cover"
                            />
                          ) : (
                            <ImageOff className="h-3.5 w-3.5 text-muted-foreground/60" />
                          )}
                        </div>
                        <div className="min-w-0">
                          <span className="flex items-center gap-2">
                            {p.nombre}
                            {p.tipo === "SERVICIO" && <Badge tone="info">Servicio</Badge>}
                          </span>
                          {p.marca && (
                            <div className="text-xs text-muted-foreground">{p.marca}</div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-muted-foreground">
                      {p.categoria?.nombre ?? "—"}
                    </td>
                    <td className="tabular px-4 py-2.5 text-right">
                      {p.tipo === "SERVICIO" ? (
                        <span className="text-muted-foreground">—</span>
                      ) : (
                        <>
                          <span className={p.sin_stock ? "font-semibold text-state-danger" : ""}>
                            {cantidad(p.stock_actual)}
                          </span>
                          {Number(p.stock_minimo) > 0 && (
                            <div className="text-xs text-muted-foreground">
                              mín. {cantidad(p.stock_minimo)}
                            </div>
                          )}
                        </>
                      )}
                    </td>
                    <td className="tabular px-4 py-2.5 text-right text-muted-foreground">
                      {soles(p.precio_compra)}
                    </td>
                    <td className="tabular px-4 py-2.5 text-right">
                      {soles(p.precio_venta)}
                      {p.margen && (
                        <div className="text-xs text-muted-foreground">+{p.margen}%</div>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      {!p.is_active ? (
                        <Badge tone="neutral">Archivado</Badge>
                      ) : p.tipo === "SERVICIO" ? (
                        <Badge tone="success">Disponible</Badge>
                      ) : p.sin_stock ? (
                        <Badge tone="danger">Sin stock</Badge>
                      ) : p.bajo_minimo ? (
                        <Badge tone="warning">Bajo mínimo</Badge>
                      ) : (
                        <Badge tone="success">Disponible</Badge>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex justify-end gap-1">
                        {/* Un servicio no tiene stock que mover: el botón se
                            omite en vez de mostrar un modal que fallaría. */}
                        {canAjustar && p.tipo !== "SERVICIO" && (
                          <button
                            onClick={() => setMovProducto(p)}
                            className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                            title="Registrar movimiento de stock"
                            aria-label={`Mover stock de ${p.sku}`}
                          >
                            <ArrowLeftRight className="h-3.5 w-3.5" />
                          </button>
                        )}
                        {canEdit && (
                          <button
                            onClick={() => {
                              setEditando(p)
                              setFormOpen(true)
                            }}
                            className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                            title="Editar"
                            aria-label={`Editar ${p.sku}`}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                        )}
                        {canEdit && (
                          <button
                            onClick={() =>
                              archivar.mutate({ id: p.id, activo: !p.is_active })
                            }
                            disabled={archivar.isPending}
                            className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                            title={
                              p.is_active
                                ? "Archivar: sale del catálogo pero conserva su historial"
                                : "Restaurar al catálogo"
                            }
                            aria-label={`${p.is_active ? "Archivar" : "Restaurar"} ${p.sku}`}
                          >
                            {p.is_active ? (
                              <Archive className="h-3.5 w-3.5" />
                            ) : (
                              <ArchiveRestore className="h-3.5 w-3.5" />
                            )}
                          </button>
                        )}
                        {canDelete && (
                          <button
                            onClick={() => {
                              eliminar.reset()
                              setPorEliminar(p)
                            }}
                            className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-state-danger"
                            title="Eliminar definitivamente"
                            aria-label={`Eliminar ${p.sku}`}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {items.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-4 py-12 text-center text-sm text-muted-foreground">
                      {debounced
                        ? `Sin resultados para "${debounced}".`
                        : tab === "alertas"
                          ? "Ningún producto necesita reposición."
                          : tab === "inactivos"
                            ? "No hay nada archivado."
                            : tipo === "SERVICIO"
                            ? "Aún no hay servicios. Créalos con «Nuevo producto» y elige el tipo Servicio."
                            : "Aún no hay productos. Puedes cargarlos con «Importar Excel»."}
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
            etiqueta="productos"
          />
        </div>
      )}

      <ProductoFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        producto={editando}
      />
      <MovimientoModal
        open={Boolean(movProducto)}
        onClose={() => setMovProducto(null)}
        producto={movProducto}
      />
      <ImportarModal open={importarOpen} onClose={() => setImportarOpen(false)} />

      <ConfirmarEliminar
        open={Boolean(porEliminar)}
        onClose={() => setPorEliminar(null)}
        titulo="Eliminar definitivamente"
        subtitulo={porEliminar ? `${porEliminar.sku} · ${porEliminar.nombre}` : undefined}
        error={eliminar.isError ? apiErrorMessage(eliminar.error, "No se pudo eliminar") : null}
        cargando={eliminar.isPending}
        onEliminar={() => porEliminar && eliminar.mutate(porEliminar.id)}
        onArchivar={
          porEliminar?.is_active
            ? () => {
                archivar.mutate({ id: porEliminar.id, activo: false })
                setPorEliminar(null)
              }
            : undefined
        }
      >
        Se borra el ítem junto con su kardex y su foto, y no se puede deshacer. Si ya se
        vendió o se usó en una ficha, el sistema lo impedirá: en ese caso{" "}
        <strong className="text-foreground">archívalo</strong>, así desaparece del catálogo
        pero sus documentos siguen cuadrando.
      </ConfirmarEliminar>
    </div>
  )
}
