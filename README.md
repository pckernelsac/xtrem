# Zona Xtrema Bikes & Componentes — ERP

ERP web para tienda + taller de bicicletas: fichas de mantenimiento, inventario,
ventas, caja y facturación electrónica SUNAT vía FactPro.

## Stack

| Capa | Tecnología |
|---|---|
| Frontend | React 19 + TypeScript + Vite 8 |
| Estilos | Tailwind CSS v4 |
| Estado servidor | TanStack Query |
| Estado cliente | Zustand |
| Backend | FastAPI + SQLAlchemy 2.x |
| Base de datos | PostgreSQL 16 |
| Migraciones | Alembic |
| Contenedores | Docker Compose |

## Estructura

```
zonaxtrema/
├── backend/          FastAPI + SQLAlchemy + Alembic
│   ├── app/
│   │   ├── core/     configuración (settings, seguridad)
│   │   ├── db/       Base declarativa, sesión
│   │   ├── models/   modelos ORM (registro central para Alembic)
│   │   ├── schemas/  Pydantic
│   │   ├── api/      routers
│   │   └── services/ lógica de negocio / integraciones
│   └── alembic/      migraciones
├── frontend/         React + Vite
│   └── src/
│       ├── components/ui/skeleton/   skeletons reutilizables
│       └── lib/      api, theme, utils
└── docker-compose.yml
```

## Arranque

Requisitos: Docker Desktop, Node 20+.

```bash
cp .env.example .env
cp backend/.env.example backend/.env

# Backend + Postgres
docker compose up -d --build

# Frontend
cd frontend
npm install
npm run dev
```

- Frontend: http://localhost:5173
- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Postgres: `localhost:5433` (5433 en el host para no chocar con un Postgres local)

## Verificación

```bash
curl http://localhost:8000/health       # {"status":"ok",...}
curl http://localhost:8000/health/db    # {"status":"ok","database":"zonaxtrema"}
curl http://localhost:5173/health       # mismo resultado vía proxy de Vite
```

En http://localhost:5173 deberías ver dos tarjetas en **OK** (API y PostgreSQL),
el toggle de modo oscuro funcionando, y el skeleton de tabla de referencia.

## Primer acceso

Tras `docker compose up -d`, aplica migraciones y siembra datos base:

```bash
docker compose exec zx_api alembic upgrade head
docker compose exec zx_api python -m app.db.seed
```

El seed crea el catálogo de permisos, los 4 roles de sistema y el usuario
administrador. **Imprime una contraseña generada una sola vez** — cópiala.
Para fijarla tú mismo: `ADMIN_EMAIL=... ADMIN_PASSWORD=... python -m app.db.seed`.

El seed es idempotente: reejecutarlo agrega permisos nuevos del catálogo sin
pisar los ajustes que hayas hecho a los roles desde la UI.

## Autorización

Permisos granulares con formato `<modulo>.<accion>` (`clientes.crear`,
`fichas.cambiar_estado`, …). El catálogo vive en `backend/app/core/permissions.py`
y es la fuente de verdad; el seed sincroniza la tabla `permissions` contra él.

- `roles` ← M2M → `permissions`; cada `user` tiene un `role_id`.
- Backend: `Depends(require_permission("clientes.crear"))` en cada endpoint.
- Frontend: `usePermission(code)` sólo pinta/oculta UI — **el backend siempre revalida**.

Reglas de seguridad implementadas:

- El rol `administrador` no admite recorte de permisos (evita dejar el sistema sin dueño).
- Los roles de sistema no se renombran ni se borran.
- Un rol con usuarios asignados no se puede eliminar.
- Nadie puede desactivarse ni cambiarse el rol a sí mismo.
- Los usuarios se dan de baja lógica, no se borran (quedan referenciados por fichas y ventas).

## Clientes y bicicletas

Documentos validados según formato peruano: DNI 8 dígitos, RUC 11, CE 9–12,
Pasaporte 6–12. La unicidad es por par `(tipo_documento, numero_documento)`,
así que el mismo número puede existir como DNI y como RUC.

Los N° de serie se normalizan a mayúsculas sin espacios y son únicos mediante
**índice parcial** (`WHERE numero_serie IS NOT NULL`): muchas bicis llegan sin
serie legible y varios NULL no deben colisionar entre sí.

Bajas lógicas en todo el módulo. Desactivar un cliente desactiva sus bicicletas
en cascada; reasignar una bici a otro dueño la desvincula de esa cascada.

El endpoint `GET /bicicletas/{id}` devuelve un campo `historial`: hoy sólo el
evento de alta, y las fichas (Fase 3) y ventas (Fase 5) se sumarán a ese feed.

## Fichas de mantenimiento

Correlativo de 6 dígitos desde una **secuencia de Postgres** (`ficha_numero_seq`),
no `MAX(numero)+1`: dos recepciones simultáneas nunca reciben el mismo número.

Estados: Recibida → En revisión → Esperando repuestos → En reparación →
Lista para entregar → Entregada. `Entregada` y `Cancelada` son finales: la ficha
deja de admitir ediciones, cambios de estado y firmas. Cada transición queda en
`ficha_estados_log` con usuario, fecha y comentario.

No se puede marcar **Entregada** sin las dos firmas registradas: la ficha firmada
es el respaldo de la entrega.

Las firmas se capturan en canvas y se guardan como data URL PNG. Se validan
decodificándolas con Pillow al guardar; un PNG corrupto dejaría la ficha
imposible de imprimir para siempre.

### Compartir por WhatsApp

`POST /fichas/{id}/compartir` devuelve el enlace público del PDF y un enlace
`wa.me` con el mensaje ya redactado. **No se envía nada desde el servidor**: el
enlace lo abre quien atiende, así que el mensaje sale desde el teléfono de la
tienda y no hace falta la API de WhatsApp Business.

El PDF queda accesible con un JWT de tipo `print` en la query (`?t=...`), válido
7 días (`PRINT_TOKEN_EXPIRE_MINUTES`) y atado a esa única ficha. Los teléfonos se
normalizan a formato peruano: `987 654 321`, `+51 987-654-321` y `(0051)…`
terminan todos en `51987654321`.

> `PUBLIC_BASE_URL` debe apuntar al dominio que ve el cliente, no a `localhost`,
> o el enlace no abrirá desde su teléfono.

### Ticket térmico de 80 mm

`GET /fichas/{id}/ticket` genera el ticket para impresora térmica.

WeasyPrint **no acepta `size: 80mm auto`** (descarta la regla y cae a A4), así
que el ticket se renderiza dos veces: la primera sobre una página de 3000 mm
sólo para medir dónde termina el contenido, la segunda con el alto exacto. Sin
eso, cada ticket saldría con decenas de centímetros de papel en blanco.

El QR apunta a la ruta corta `/f/{codigo}`, no al JWT: con el token la URL da un
QR de versión 14 (~0.34 mm por módulo en 26 mm), al límite de una térmica de
203 dpi; el código corto lo baja a versión 3 (~0.79 mm). El código también se
imprime en texto, por si la cámara no lee el QR.

`GET /f/{codigo}` es público y devuelve la ficha (`?formato=ticket` para el
ticket). El código son 10 caracteres de un alfabeto sin `0/O`, `1/I/L` ni `8/B`,
para poder dictarlo por teléfono sin confusiones.

### PDF

`GET /fichas/{id}/pdf` genera con WeasyPrint una réplica del formato impreso
(`zona.jpeg`). La plantilla está en `app/templates/ficha.html`, los iconos SVG en
`_iconos.html` y los assets de marca en `app/assets/`.

> Los logos se recortaron del JPEG de la ficha, así que su resolución es
> limitada. Reemplaza `app/assets/logo_zonaxtrema.png` y `emblema_x.png` por los
> originales vectoriales cuando estén disponibles.

Para revisar el resultado durante el desarrollo:

```bash
docker compose exec zx_api pdftoppm -png -r 110 /tmp/ficha.pdf /tmp/pag
docker compose cp zx_api:/tmp/pag-1.png ./revision.png
```

## Inventario y kardex

`productos.stock_actual` está denormalizado por velocidad, pero la **fuente de
verdad es el kardex**: cada asiento guarda el stock antes y después, así que el
saldo siempre se puede reconstruir y auditar con
`GET /inventario/productos/{id}/auditoria`.

Todo cambio de existencias pasa por `services/inventario.py`, que bloquea la
fila con `SELECT ... FOR UPDATE`. Sin ese bloqueo, dos salidas simultáneas leen
el mismo stock inicial y la segunda pisa a la primera. Verificado con 10
peticiones concurrentes: las 10 se aplican y el saldo queda exacto; y con 10
salidas de 2 sobre stock 5, sólo 2 pasan y el resto recibe 409.

> El `lazy="joined"` de la categoría rompe el bloqueo: Postgres rechaza
> `FOR UPDATE` sobre el lado nullable de un OUTER JOIN. Por eso la consulta de
> bloqueo lo anula con `lazyload`.

Tipos de movimiento: **ENTRADA** (compra, devolución), **SALIDA** (venta,
consumo, merma) y **AJUSTE** (conteo físico). En un ajuste, `cantidad` es el
stock **contado**, no la diferencia: quien inventaría anota lo que ve en el
estante. Una entrada con `costo_unitario` actualiza el precio de compra.

`stock_minimo = 0` significa "sin control de stock", no "alertar siempre".

### Fichas ↔ inventario

Una línea de repuesto puede enlazarse a un producto (`producto_id`) o quedar
como texto libre. **Sólo las líneas enlazadas mueven stock.**

El descuento ocurre **al anotar el repuesto en la ficha, no al entregarla**: el
técnico ya sacó la pieza del estante en ese momento. Si se esperara a la
entrega, el sistema mostraría existencias que físicamente ya no están y el
mostrador podría vender lo mismo dos veces.

Al editar los repuestos se aplica **la diferencia**, no un borrado y recarga:
reenviar las mismas líneas no genera asientos falsos, subir la cantidad
descuenta el delta y bajarla devuelve al almacén. Cancelar una ficha (por
`DELETE` o por `/estado`) reintegra todo lo enlazado.

Cada movimiento queda en el kardex con `referencia = FICHA-<numero>`, así que
todo consumo se puede rastrear hasta su orden de trabajo.

> Los bloqueos se toman **ordenados por id de producto**. Dos fichas que tocan
> los mismos productos a la vez los bloquearían en orden distinto y podrían
> interbloquearse.

### Importación desde Excel

`POST /inventario/importar` corre en **modo prueba por defecto**: valida y
devuelve el reporte fila por fila sin escribir nada. Recién con
`modo_prueba=false` aplica, y lo hace **todo o nada** — un archivo con un solo
error no deja medio inventario cargado.

El stock del archivo entra como AJUSTE con su asiento de kardex, nunca pisando
el saldo en silencio. Las categorías nuevas se crean solas.

`GET /inventario/plantilla-excel` descarga un .xlsx de ejemplo con las cabeceras
exactas; el importador acepta variantes con y sin tilde y coma decimal.

## Ventas y caja

Una **venta** descuenta stock y entra a la caja en el acto. Una **cotización**
es una promesa de precio: no toca ni el almacén ni el dinero hasta convertirse
en venta, y conserva su número (`COT-…` → sigue siendo `COT-…`) para no perder
el rastro de lo que el cliente aceptó. Correlativos separados por serie
(`V-…`, `COT-…`, `C-…` de caja), cada uno con su secuencia Postgres.

Una venta confirmada **no se edita**: ya movió stock y dinero. Para corregirla
se anula (devuelve mercadería y efectivo) y se emite otra. Sólo las cotizaciones
pendientes son editables.

### El arqueo sólo cuenta efectivo

El cajón físico sólo recibe efectivo, así que el arqueo compara **lo contado
contra el efectivo esperado**. Yape, Plin, tarjeta y transferencia se registran
por método para el reporte del día, pero **no entran al conteo**: sumarlos haría
que la caja nunca cuadre.

- El efectivo **exige caja abierta**; los métodos digitales no.
- Al cerrar, el `monto_esperado` se **congela**. Si mañana se anula una venta de
  hoy, el arqueo de hoy no cambia; la devolución sale de la caja abierta ese día.
- No se puede retirar más efectivo del que hay: el cajón nunca queda negativo.

### Escaneo en el punto de venta

`GET /inventario/productos/buscar?codigo=…` resuelve un código de barras (o un
SKU tecleado) a un único producto. El mostrador enfoca siempre el campo de
escaneo; escanear dos veces el mismo producto suma cantidad en vez de repetir
la línea.

### Concurrencia

Dos bugs de concurrencia que encontré probando con hilos, no leyendo el código:

1. **Deadlock**: el INSERT de una línea de venta toma un lock compartido sobre
   `productos` por la clave foránea; subirlo después a `FOR UPDATE` interbloquea
   dos ventas del mismo producto. Se corrige **bloqueando los productos antes de
   insertar** (`bloquear_productos`), siempre en orden por id.
2. Un pago digital no se reflejaba en la caja aunque hubiera sesión abierta.

Verificado: 6 ventas simultáneas de 3 sobre stock 10 → 3 pasan, 3 reciben `409`
limpio (no 500), stock final exacto y kardex cuadrado.

## Facturación electrónica (FactPro)

Integración con FactPro para emitir comprobantes a SUNAT. La lógica de mapeo al
JSON de FactPro está en `services/facturacion.py`; el cliente HTTP en
`services/factpro_client.py`; los catálogos SUNAT en `services/factpro_catalogos.py`.

**Tipo de comprobante automático**: factura si el cliente tiene RUC, boleta en
cualquier otro caso. Una boleta sin cliente identificado (público general) no
puede superar S/ 700 — límite de SUNAT.

Flujo: venta confirmada → `POST /facturacion/emitir` → construir JSON → enviar a
FactPro → persistir `ComprobanteElectronico` con XML/PDF/CDR, hash, QR y estado
SUNAT. La vista **Documentos electrónicos** replica el patrón de FactPro: tabs
por estado con contador, tabla densa y acciones XML · PDF · CDR por fila.

Anular un comprobante comunica la baja a SUNAT (`/anular`) pero **no revierte la
venta** (stock ni caja): son operaciones tributaria y comercial independientes.

### Autenticación y modo

El **Bearer es el token de EMPRESA** (el token de usuario devuelve 401). Se
configura en `FACTPRO_TOKEN`.

**Sin token, el sistema opera en modo simulación**: construye y persiste los
comprobantes con la estructura real de FactPro pero sin enviarlos a SUNAT; los
marca `es_simulado = true` y la UI muestra un aviso. Con token, emite de verdad.

### Verificado contra la API real (cuenta demo de FactPro)

Se probó el flujo completo contra `api.factpro.la` (19 pruebas, cuenta en modo
demo → sin efecto legal ante SUNAT):

- **Boleta** (cliente DNI) y **factura** (cliente RUC) emitidas y ACEPTADAS.
- El **PDF real se descarga** desde la URL que devuelve FactPro (HTTP 200 `%PDF`).
- **Consultar** y **anular** (comunicación de baja) funcionan.

Hallazgos que corrigieron supuestos previos:

- **FactPro usa su propio catálogo de tipo de documento, no el de SUNAT**:
  DNI = `"1"`, **RUC = `"4"`** (no `"6"`, que da "tipo incorrecto"). La boleta a
  **público general** (venta de mostrador sin cliente) tampoco acepta el `"0"`
  del catálogo SUNAT: FactPro exige tipo DNI `"1"` con número `"00000000"`. CE y
  pasaporte quedan como código plausible pero **sin confirmar** — verificar
  antes de facturar a un extranjero. Todo centralizado en `factpro_catalogos.py`.
- Los **errores** llegan como `{"errors":[{"message":"…"}]}`, no como el
  `mensaje` plano que mostraba la doc. El cliente contempla ambas formas.
- Las **rutas** reales son `/anular` y `/consulta` (POST), no `/anulacion` ni
  `/consultar`; configurables en settings.

### Pendiente para producción

- La cuenta demo pertenece a un RUC de prueba de FactPro (`20600340647`). Para
  emitir como Zona Xtrema hay que crear la empresa con RUC `10431869662`,
  cargar su certificado digital y **pasar la cuenta de demo a producción**
  (activa la validez ante SUNAT; recomiendan activar la firma 24–48 h antes).
- Confirmar los códigos de CE y pasaporte.
- Nota de crédito queda modelada (`TipoComprobante.NOTA_CREDITO`) pero su emisión
  como flujo propio se difiere; hoy la baja se hace por `/anular`.

## Reportes y vista pública

### Reportes exportables

Tres reportes bajo `/reportes`, cada uno con export:

- **Ventas** por rango: total, ticket promedio, serie día a día (con los días
  vacíos en cero para no mentir en el gráfico) y desglose por método de pago.
  Export a **Excel** y **PDF** (con gráfico de barras dibujado en HTML/CSS, sin
  librerías de charting).
- **Productos más vendidos**: ranking por importe en el rango. Export Excel.
- **Inventario valorizado**: foto actual del valor a costo y productos bajo
  mínimo / sin stock. Export Excel.

Los totales de venta se suman en Python (son propiedades, no columnas); el
ranking se agrega en SQL. El rango se acota a un año.

### Vista pública del QR (el diferenciador)

El QR del ticket térmico apunta a `/f/{codigo}`, que ahora sirve una **página
HTML pensada para el celular** (antes devolvía el PDF; sigue disponible con
`?formato=pdf` o `?formato=ticket`). Es server-rendered (Jinja2), con la marca
Zona Xtrema, y muestra al cliente el estado de su bici, servicios, trabajo
realizado, repuestos, garantía (con fecha de vencimiento), el comprobante
electrónico enlazado si se emitió, y el seguimiento de estados.

**Sólo expone lo que el cliente puede ver de SU bicicleta** — nunca precios de
costo, notas internas ni datos de otros clientes. El código corto es la única
credencial, igual que la copia impresa que ya tiene en la mano.

## Pulido (Fase 8)

### Auditoría

Un middleware (`core/audit.py`) registra **cada petición que cambia estado**
(POST/PATCH/PUT/DELETE) en la tabla `auditoria`: quién, qué ruta, módulo, código
de respuesta, duración e IP. **Nunca lee el cuerpo** de la petición, así no
filtra contraseñas ni firmas. Los GET no se registran (serían ruido). Se ve en
`/auditoria` (permiso `auditoria.ver`, sólo administrador por defecto), con
filtros por módulo, usuario y sólo-errores.

### Notificaciones

`GET /notificaciones` calcula en vivo alertas accionables —stock bajo/agotado,
fichas listas para entregar, cotizaciones vencidas, caja sin cerrar, comprobantes
con error— y **respeta los permisos**: a un técnico no se le avisa de caja. La
campana del header las muestra con contador y refresca cada minuto.

### Backups

`scripts/backup.sh` genera un dump comprimido con `pg_dump --clean --if-exists`
y conserva los últimos 14. `scripts/restore.sh` restaura uno (con confirmación).

```bash
./scripts/backup.sh                          # crea backups/zonaxtrema_<fecha>.sql.gz
./scripts/restore.sh backups/zonaxtrema_….sql.gz
```

Automatizar en el servidor con cron:

```cron
0 2 * * *  cd /ruta/zonaxtrema && ./scripts/backup.sh >> backups/backup.log 2>&1
```

### PWA

La app es **instalable** (móvil y escritorio): `manifest.webmanifest`, iconos de
marca y un service worker conservador (`public/sw.js`) que nunca cachea la API,
usa network-first para la navegación y cache-first sólo para los assets con hash
de Vite —así no sirve versiones viejas del sistema—. El SW se registra sólo en
producción para no interferir el HMR de desarrollo.

### Swagger / OpenAPI

`/docs` (Swagger UI) y `/redoc` con descripción rica, tags documentados, datos de
contacto y **esquema de seguridad Bearer JWT**: el botón *Authorize* 🔒 permite
pegar el token y probar los endpoints protegidos desde el navegador.

## Consulta de DNI/RUC (RENIEC/SUNAT)

El buscador de clientes busca **sólo en la base local**. Para **autocompletar el
nombre desde el documento** (DNI → RENIEC, RUC → SUNAT) se usa la API de
consultas de FactPro (`consultas.factpro.la`), que es un **producto aparte** con
**su propio token** — distinto al de facturación, y que el de facturación NO
sirve (da "Token incorrecto").

- Configurar `FACTPRO_CONSULTAS_TOKEN` tras activar el producto en FactPro.
- **Sin token**, el endpoint responde 503 con mensaje claro y el botón "Buscar"
  del formulario de cliente **no se muestra** (degradación limpia).
- Endpoints: `GET /clientes/consulta-documento/disponible` (¿hay token?) y
  `GET /clientes/consulta-documento?tipo=DNI|RUC&numero=…`. Sólo DNI y RUC tienen
  padrón público.

## Datos del negocio

Tomados de la proforma impresa, para Fases 5–6:

- RUC **10431869662** · Av. San Carlos N° 177, Huancayo · www.zonaxtrema.pe
- BCP Ahorro Soles 35501413975094 · CCI 00235510141397509467
- Scotiabank Ahorro Soles 9430100496 · CCI 00994320943010049627
- Garantía de mantenimiento general: 7 días desde la entrega
- Recojo dentro de 2 semanas; pasado ese plazo se aplica 20% del costo total

## Migraciones

```bash
docker compose exec zx_api alembic revision --autogenerate -m "mensaje"
docker compose exec zx_api alembic upgrade head
docker compose exec zx_api alembic current
```

Todo modelo nuevo debe importarse en `backend/app/models/__init__.py` para que
`--autogenerate` lo detecte.

## Convenciones de diseño

- Paleta: negro `#0a0a0a` / `#161616`, rojo marca `#e01e26`. Sin azul por defecto.
- Sidebar siempre oscura en ambos temas; ítem activo en rojo.
- Tablas densas, cabecera en `bg-secondary`, filas zebra sutiles, badges pill.
- Montos con la clase `.tabular` (`font-variant-numeric: tabular-nums`).
- **Nunca spinners**: todo estado de carga usa los componentes de
  `src/components/ui/skeleton/` con la forma del contenido real.

## Aislamiento en Docker

Los recursos llevan prefijo `zx_` (`zx_db`, `zx_api`, `zx_net`, `zx_pgdata`)
para convivir con otros stacks en el mismo host o servidor.

## Fases

- [x] **Fase 0** — Setup: monorepo, Docker Compose, Alembic, tema y skeletons
- [x] **Fase 1** — Auth JWT, roles en tabla con permisos granulares, usuarios
- [x] **Fase 2** — Clientes y bicicletas (CRUD, búsqueda, historial por bici)
- [x] **Fase 3** — Fichas de mantenimiento + PDF con el diseño de la ficha impresa
- [x] **Fase 4** — Inventario: SKU, categorías, kardex, alertas, importación Excel
- [x] **Fase 5** — Ventas, cotizaciones, punto de venta con escaneo, caja y arqueo
- [x] **Fase 6** — Facturación electrónica FactPro (boleta/factura, anulación, modo simulación)
- [x] **Fase 7** — Reportes exportables (PDF/Excel) y vista pública del QR
- [x] **Fase 8** — Pulido: auditoría, notificaciones, backups, PWA, Swagger completo
