import { useEffect, useRef, useState } from "react"
import { Eraser } from "lucide-react"

import { Button } from "@/components/ui/Form"

/**
 * Captura de firma sobre canvas, con soporte de mouse y táctil (tablet en
 * mostrador). Devuelve un data URL PNG que el backend valida y embebe en el PDF.
 */
export function SignaturePad({
  value,
  onChange,
  disabled,
}: {
  value: string | null
  onChange: (dataUrl: string | null) => void
  disabled?: boolean
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const dibujando = useRef(false)
  const [vacio, setVacio] = useState(!value)

  // El canvas se dimensiona por DPR para que el trazo no salga pixelado
  // en pantallas retina ni al escalarlo dentro del PDF.
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()
    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr

    const ctx = canvas.getContext("2d")
    if (!ctx) return
    ctx.scale(dpr, dpr)
    ctx.lineWidth = 2
    ctx.lineCap = "round"
    ctx.lineJoin = "round"
    ctx.strokeStyle = "#0f0f28"

    if (value) {
      const img = new Image()
      img.onload = () => ctx.drawImage(img, 0, 0, rect.width, rect.height)
      img.src = value
      setVacio(false)
    }
  }, [value])

  const punto = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    return { x: e.clientX - rect.left, y: e.clientY - rect.top }
  }

  const empezar = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (disabled) return
    e.currentTarget.setPointerCapture(e.pointerId)
    const ctx = canvasRef.current?.getContext("2d")
    if (!ctx) return
    const p = punto(e)
    ctx.beginPath()
    ctx.moveTo(p.x, p.y)
    dibujando.current = true
  }

  const mover = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!dibujando.current || disabled) return
    const ctx = canvasRef.current?.getContext("2d")
    if (!ctx) return
    const p = punto(e)
    ctx.lineTo(p.x, p.y)
    ctx.stroke()
    setVacio(false)
  }

  const terminar = () => {
    if (!dibujando.current) return
    dibujando.current = false
    const canvas = canvasRef.current
    if (canvas) onChange(canvas.toDataURL("image/png"))
  }

  const limpiar = () => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext("2d")
    if (!canvas || !ctx) return
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    setVacio(true)
    onChange(null)
  }

  return (
    <div>
      <div className="relative rounded-md border border-border bg-background">
        <canvas
          ref={canvasRef}
          onPointerDown={empezar}
          onPointerMove={mover}
          onPointerUp={terminar}
          onPointerLeave={terminar}
          className="h-32 w-full touch-none rounded-md"
          style={{ cursor: disabled ? "not-allowed" : "crosshair" }}
        />
        {vacio && (
          <span className="pointer-events-none absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">
            {disabled ? "Firma bloqueada" : "Firma aquí"}
          </span>
        )}
        <div className="pointer-events-none absolute inset-x-6 bottom-5 border-b border-dashed border-border" />
      </div>

      {!disabled && (
        <Button
          type="button"
          variant="ghost"
          onClick={limpiar}
          className="mt-1.5 px-2 py-1 text-xs"
        >
          <Eraser className="h-3.5 w-3.5" />
          Borrar
        </Button>
      )}
    </div>
  )
}
