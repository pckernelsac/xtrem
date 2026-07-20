import { cn } from "@/lib/utils"

export type FilterTab<T extends string> = {
  value: T
  label: string
  count: number
}

/**
 * Tabs de filtro con contador, el patrón "Todos (17) · Registrado (11) · ..."
 * que se repite en órdenes, ventas y documentos electrónicos.
 */
export function FilterTabs<T extends string>({
  tabs,
  value,
  onChange,
  loading = false,
}: {
  tabs: FilterTab<T>[]
  value: T
  onChange: (v: T) => void
  loading?: boolean
}) {
  return (
    <div className="flex flex-wrap items-center gap-1 border-b border-border">
      {tabs.map((tab) => {
        const active = tab.value === value
        return (
          <button
            key={tab.value}
            onClick={() => onChange(tab.value)}
            className={cn(
              "-mb-px flex items-center gap-2 border-b-2 px-3 py-2 text-sm transition",
              active
                ? "border-primary font-medium text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {tab.label}
            <span
              className={cn(
                "tabular rounded-full px-1.5 py-0.5 text-xs",
                active ? "bg-primary/12 text-primary" : "bg-muted text-muted-foreground",
              )}
            >
              {loading ? "–" : tab.count}
            </span>
          </button>
        )
      })}
    </div>
  )
}
