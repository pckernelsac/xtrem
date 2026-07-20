import { cn } from "@/lib/utils"
import { Skeleton } from "./Skeleton"

/**
 * Fila de skeleton. `widths` define el ancho de cada celda para que el
 * placeholder tenga la misma forma que la tabla real (mismas columnas).
 */
export function SkeletonRow({
  widths = ["w-24", "w-40", "w-32", "w-20"],
  className,
}: {
  widths?: string[]
  className?: string
}) {
  return (
    <tr className={cn("border-b border-border", className)}>
      {widths.map((w, i) => (
        <td key={i} className="px-4 py-3">
          <Skeleton className={cn("h-4", w)} />
        </td>
      ))}
    </tr>
  )
}

export function SkeletonTable({
  rows = 8,
  columns = ["w-24", "w-40", "w-32", "w-20"],
  headers,
}: {
  rows?: number
  columns?: string[]
  headers?: string[]
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-secondary">
          <tr>
            {(headers ?? columns).map((h, i) => (
              <th
                key={i}
                className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground"
              >
                {headers ? h : <Skeleton className="h-3 w-20" />}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, i) => (
            <SkeletonRow key={i} widths={columns} className={i % 2 === 1 ? "bg-muted/30" : ""} />
          ))}
        </tbody>
      </table>
    </div>
  )
}
