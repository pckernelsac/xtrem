import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { AlertCircle, Eye, EyeOff, Loader2, Lock } from "lucide-react"

import { api, API_PREFIX, apiErrorMessage } from "@/lib/api"
import { useAuth, type Me } from "@/lib/auth"

export default function LoginPage() {
  const navigate = useNavigate()
  const { setTokens, setMe } = useAuth()

  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)

  const login = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ access_token: string; refresh_token: string }>(
        `${API_PREFIX}/auth/login`,
        { email, password },
      )
      setTokens(data.access_token, data.refresh_token)
      const me = await api.get<Me>(`${API_PREFIX}/auth/me`)
      return me.data
    },
    onSuccess: (me) => {
      setMe(me)
      navigate("/", { replace: true })
    },
  })

  return (
    // Página de acceso: siempre clara, independiente del modo del sistema.
    <div className="flex min-h-screen items-center justify-center bg-zinc-100 px-4 py-10">
      <div className="w-full max-w-sm">
        {/* Marca */}
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary text-2xl font-extrabold tracking-tight text-white shadow-lg shadow-primary/25">
            ZX
          </div>
          <h1 className="mt-4 text-2xl font-bold text-zinc-900">Zona Xtrema</h1>
          <p className="text-sm text-zinc-500">Bikes &amp; Componentes</p>
        </div>

        {/* Tarjeta */}
        <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-xl shadow-zinc-900/5">
          {/* Franja de marca superior */}
          <div className="h-1.5 bg-primary" />

          <form
            onSubmit={(e) => {
              e.preventDefault()
              login.mutate()
            }}
            className="p-7"
          >
            <h2 className="text-lg font-semibold text-zinc-900">Iniciar sesión</h2>
            <p className="mt-1 text-sm text-zinc-500">Ingresa con tu cuenta del sistema</p>

            <label className="mt-6 block text-sm font-medium text-zinc-700" htmlFor="email">
              Correo
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="usuario@zonaxtrema.pe"
              className="mt-1.5 w-full rounded-lg border border-zinc-300 bg-white px-3.5 py-2.5 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            />

            <label className="mt-4 block text-sm font-medium text-zinc-700" htmlFor="password">
              Contraseña
            </label>
            <div className="relative mt-1.5">
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full rounded-lg border border-zinc-300 bg-white px-3.5 py-2.5 pr-10 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 text-zinc-400 hover:text-zinc-600"
                aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>

            {login.isError && (
              <div
                role="alert"
                className="mt-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700"
              >
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{apiErrorMessage(login.error, "No se pudo iniciar sesión")}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={login.isPending}
              className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-primary/90 disabled:opacity-60"
            >
              {login.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              {login.isPending ? "Ingresando..." : "Ingresar"}
            </button>
          </form>
        </div>

        <p className="mt-6 flex items-center justify-center gap-1.5 text-center text-xs text-zinc-400">
          <Lock className="h-3 w-3" />
          Acceso seguro · Zona Xtrema ERP
        </p>
      </div>
    </div>
  )
}
