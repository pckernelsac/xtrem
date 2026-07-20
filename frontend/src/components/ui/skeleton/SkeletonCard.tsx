import { cn } from "@/lib/utils"
import { Skeleton } from "./Skeleton"

export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={cn("rounded-lg border border-border bg-card p-5", className)}>
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="mt-3 h-3 w-full" />
      <Skeleton className="mt-2 h-3 w-4/5" />
      <Skeleton className="mt-2 h-3 w-2/3" />
    </div>
  )
}

/** Card de KPI del dashboard: label corto arriba, número grande, delta abajo. */
export function SkeletonStatCard({ className }: { className?: string }) {
  return (
    <div className={cn("rounded-lg border border-border bg-card p-5", className)}>
      <div className="flex items-start justify-between">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-8 w-8 rounded-md" />
      </div>
      <Skeleton className="mt-4 h-8 w-28" />
      <Skeleton className="mt-2 h-3 w-20" />
    </div>
  )
}

/** Placeholder de gráfico: barras de alturas variables. */
export function SkeletonChart({ className, bars = 12 }: { className?: string; bars?: number }) {
  const heights = ["h-16", "h-24", "h-32", "h-20", "h-28", "h-12", "h-36"]
  return (
    <div className={cn("rounded-lg border border-border bg-card p-5", className)}>
      <Skeleton className="h-4 w-40" />
      <div className="mt-6 flex items-end gap-2">
        {Array.from({ length: bars }).map((_, i) => (
          <Skeleton key={i} className={cn("flex-1", heights[i % heights.length])} />
        ))}
      </div>
    </div>
  )
}
