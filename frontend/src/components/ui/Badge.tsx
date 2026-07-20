import { cn } from "@/lib/utils"

type Tone = "success" | "warning" | "danger" | "neutral" | "info"

const TONES: Record<Tone, string> = {
  success: "bg-state-success/12 text-state-success ring-state-success/25",
  warning: "bg-state-warning/12 text-state-warning ring-state-warning/25",
  danger: "bg-state-danger/12 text-state-danger ring-state-danger/25",
  neutral: "bg-state-neutral/12 text-state-neutral ring-state-neutral/25",
  info: "bg-state-info/12 text-state-info ring-state-info/25",
}

/** Badge pill de estado, patrón compartido por todos los listados del ERP. */
export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: Tone
  children: React.ReactNode
  className?: string
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}
