/*
 * Service worker de Zona Xtrema ERP.
 *
 * Estrategia conservadora para no servir versiones viejas del sistema:
 *  - Las peticiones a la API (/api, /f, /health) NUNCA se cachean: los datos
 *    deben ser siempre frescos.
 *  - La navegación (documentos HTML) usa network-first con respaldo a caché,
 *    para que si hay internet siempre se cargue la última versión de la app y,
 *    sin internet, al menos abra la última que se vio.
 *  - Los assets con hash (JS/CSS/íconos de Vite) se cachean cache-first: su
 *    nombre cambia en cada build, así que nunca quedan obsoletos.
 */
const CACHE = "zx-erp-v1"
const NO_CACHEAR = ["/api/", "/f/", "/health"]

self.addEventListener("install", () => self.skipWaiting())

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((claves) => Promise.all(claves.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener("fetch", (event) => {
  const { request } = event
  if (request.method !== "GET") return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return
  if (NO_CACHEAR.some((p) => url.pathname.startsWith(p))) return

  // Navegaciones: network-first.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((resp) => {
          const copia = resp.clone()
          caches.open(CACHE).then((c) => c.put(request, copia))
          return resp
        })
        .catch(() => caches.match(request).then((r) => r || caches.match("/"))),
    )
    return
  }

  // Assets: cache-first (los nombres llevan hash de contenido).
  event.respondWith(
    caches.match(request).then(
      (cacheado) =>
        cacheado ||
        fetch(request).then((resp) => {
          if (resp.ok && resp.type === "basic") {
            const copia = resp.clone()
            caches.open(CACHE).then((c) => c.put(request, copia))
          }
          return resp
        }),
    ),
  )
})
