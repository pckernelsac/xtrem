import { cn } from "@/lib/utils"

/** Bloque base: todo skeleton del sistema se compone de este primitivo. */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} {...props} />
}
