# Zona Xtrema Bikes & Componentes — ERP

ERP web para tienda + taller de bicicletas: fichas de mantenimiento, inventario,
ventas, caja y facturación electrónica SUNAT vía Nubefact.

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
deja de admitir ediciones ni cambios de estado. Cada transición queda en
`ficha_estados_log` con usuario, fecha y comentario.

El **checklist de servicios** cambió el 25-jul-2026 a los ocho actuales
(`SERVICIOS_VIGENTES` en `models/ficha.py`). Los códigos anteriores siguen en el
enum a propósito: `fichas.servicios` es JSONB y las fichas viejas los tienen
guardados, así que sacarlos del enum haría fallar la edición de esas fichas al
reenviar sus propios servicios. No se ofrecen al crear, pero se muestran —en el
formulario y en el PDF— cuando la ficha ya los traía.

**Las firmas de conformidad se retiraron** (25-jul-2026): ya no se capturan en
pantalla ni se imprimen en el PDF ni en el ticket, y marcar la entrega no exige
firma alguna. Las columnas `firma_*` y `fecha_firma` siguen en `fichas` con lo
ya registrado; no hay migración que las borre. El permiso `fichas.firmar` salió
del catálogo, así que el listado de permisos lo filtra aunque su fila siga en la
tabla.

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

## Facturación electrónica (Nubefact)

Emisión de comprobantes a SUNAT vía **Nubefact**. El proveedor es conmutable con
`FACTURADOR` (`nubefact` | `factpro`) para poder volver atrás sin desplegar
código; `services/facturacion.py` orquesta y delega en el proveedor activo:

| Pieza | Nubefact | FactPro (anterior) |
|---|---|---|
| Cliente HTTP | `nubefact_client.py` | `factpro_client.py` |
| Payload y respuesta | `nubefact_facturacion.py` | `facturacion.py` |
| Catálogos | `nubefact_catalogos.py` | `factpro_catalogos.py` |

**Tipo de comprobante automático**: factura si el cliente tiene RUC, boleta en
cualquier otro caso. Una boleta sin cliente identificado (público general) no
puede superar S/ 700 — límite de SUNAT.

Flujo: venta confirmada → `POST /facturacion/emitir` → construir JSON → enviar →
persistir `ComprobanteElectronico` con XML/PDF/CDR, hash, QR y estado SUNAT.

Anular comunica la baja a SUNAT pero **no revierte la venta** (stock ni caja):
son operaciones tributaria y comercial independientes.

### Lo que cambia respecto a FactPro

Dos diferencias de fondo, no de nombres de campo:

- **El correlativo lo lleva este sistema.** FactPro asignaba el número; Nubefact
  exige que el emisor lo mande, consecutivo desde 1 por tipo de documento. Va por
  una secuencia de Postgres por serie. Como las secuencias no retroceden en un
  `ROLLBACK`, un envío fallido dejaría un hueco —que SUNAT observa—, así que el
  reintento **reutiliza el número reservado** por el intento en `ERROR`.
- **El IGV se desglosa aquí, línea por línea.** FactPro recibía precios con IGV y
  desglosaba; Nubefact exige valor unitario sin IGV, subtotal, IGV y total por
  línea, y valida que la suma cuadre con los totales. El desglose parte del
  importe final de cada línea y saca la base por división, con el IGV por
  diferencia: así las tres cifras cuadran siempre al céntimo.

De paso se corrige un fallo que arrastraba FactPro: el **descuento global** de la
venta no viajaba al comprobante, que salía por un importe mayor al cobrado. Ahora
se prorratea entre las líneas y el resto del redondeo se carga a la mayor.

Otros cambios: la cabecera `Authorization` va **sin `Bearer`**; las cuatro
operaciones van a la misma URL distinguidas por el campo `operacion`; el tipo de
documento del cliente sigue el **catálogo 06 de SUNAT** (RUC = `6`, no el `4`
propio de FactPro) y la venta de mostrador usa el código oficial `"-"` (VARIOS)
en vez del apaño de un DNI de ceros.

**Idempotencia**: cada emisión manda un `codigo_unico`. Si el envío llega pero se
pierde la respuesta, el reintento recibe el error 23 («ya existe») y el sistema
**recupera el comprobante emitido** en vez de duplicarlo ante SUNAT.

**Anulación diferida**: Nubefact devuelve un ticket y `aceptada_por_sunat: false`
hasta que SUNAT procesa la baja. El comprobante NO se marca `ANULADO` de entrada;
queda «Baja en trámite» y se confirma al consultar el estado.

### Series

Las series **no son libres**: las habilita la cuenta del facturador, y emitir con
una que no esté dada de alta se rechaza con *«no puedes emitir comprobantes con
esta serie»*. Nubefact exige 4 caracteres exactos, empezando por `B` (boletas y
sus notas) o `F` (facturas y sus notas). Las cuentas demo traen `BBB1` y `FFF1`;
en producción se usan las autorizadas por SUNAT. Se configuran en
`SERIE_BOLETA`, `SERIE_FACTURA`, `SERIE_NC_BOLETA` y `SERIE_NC_FACTURA`.

### Autenticación y modo

`NUBEFACT_RUTA` (URL propia con UUID) y `NUBEFACT_TOKEN`, ambos del panel de
Nubefact, opción **API (Integración)**.

**Sin esas credenciales el sistema opera en modo simulación**: construye y
persiste los comprobantes con la estructura real pero sin enviarlos a SUNAT; los
marca `es_simulado = true` y la UI muestra un aviso.

### Verificado contra la API real (cuenta demo)

- Boleta a público general y **factura** a cliente con RUC emitidas; la factura
  volvió `aceptada_por_sunat: true` en el acto.
- Desglose de IGV comprobado con las ventas reales de la base y con casos límite
  (descuento global indivisible, cantidades fraccionarias, un céntimo, importes
  grandes): **cuadran todos al céntimo**.
- Recuperación de duplicado (error 23), consulta de estado, comunicación de baja,
  PDF público por `/c/{codigo}` y mensaje de WhatsApp.
- Regresión del flujo de servicios: ficha → nota de venta → boleta encima, sin
  doble cobro en caja.

### Paso de demo a producción

El **correlativo se reinicia solo**: cada serie tiene su propia secuencia
(`comprobante_<serie>_seq`), así que al cambiar `SERIE_BOLETA` de `BBB1` a `B001`
se crea una secuencia nueva y la primera boleta sale con el número 1. No hay que
tocar nada para eso.

Lo que **no** se arregla solo son los comprobantes emitidos durante las pruebas:
se quedan en la tabla y no se distinguen de los reales. El registro de ventas que
se exporta para el contador filtra por fecha de emisión, **no por serie**, así que
un periodo que abarque las pruebas las declararía ante SUNAT como válidas.

Procedimiento:

1. Cambiar las cuatro `SERIE_*` a las autorizadas y redesplegar.
2. Ejecutar el corte, que primero sólo informa:

```bash
docker compose exec zx_api python -m app.db.corte_produccion            # simulación
docker compose exec zx_api python -m app.db.corte_produccion --aplicar  # ejecuta
```

Retira los comprobantes de las series que ya no están configuradas, borra sus
secuencias y reinicia las de producción **sólo si aún no han emitido nada**, para
no romper la correlatividad de una serie ya en marcha. Las ventas no se tocan:
las que se habían facturado en pruebas vuelven a quedar pendientes y se pueden
reemitir con numeración válida.

### Pendiente para producción

- **Pasar la cuenta de Nubefact a producción** y cambiar las series demo
  (`BBB1`/`FFF1`) por las autorizadas por SUNAT. Antes de habilitarla, Nubefact
  pide emitir un juego de documentos de prueba desde el sistema.
- La migración `d1a7c3e58b46` **borra los comprobantes de FactPro** que quedaron
  sin validar y reinicia las secuencias: sin eso, la primera emisión chocaría con
  el índice único de serie y número. Las ventas no se tocan.
- Nota de crédito queda modelada y con su constructor de payload
  (`construir_payload_nota_credito`), pero el flujo propio se difiere; hoy la baja
  se hace por comunicación de baja.

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
**APIsPERU** (`dniruc.apisperu.com`), un servicio **independiente del
facturador**: si el facturador se cae, el autocompletado del mostrador sigue en
pie. Antes esto colgaba de la API de consultas de FactPro, con el efecto de que
un problema del proveedor tumbaba las dos cosas a la vez.

- Configurar `APISPERU_TOKEN` tras registrarse en apisperu.com. El token viaja
  como parámetro de la query, que es como lo exige su API.
- APIsPERU devuelve los apellidos **ya separados** del nombre de pila, así que no
  hace falta partir la cadena del padrón como exigía FactPro. El nombre se arma
  con el nombre de pila delante, para que los saludos de WhatsApp no usen el
  apellido.
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
- [x] **Fase 6** — Facturación electrónica (boleta/factura, anulación, modo simulación); migrada de FactPro a Nubefact
- [x] **Fase 7** — Reportes exportables (PDF/Excel) y vista pública del QR
- [x] **Fase 8** — Pulido: auditoría, notificaciones, backups, PWA, Swagger completo
