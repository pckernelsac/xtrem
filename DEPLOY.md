# Despliegue en Dokploy

El servidor Dokploy es **compartido con otros stacks**. Todo lo que este
proyecto crea va prefijado con `xtrem-` (servicios, red, routers de Traefik)
porque en Dokploy todos los contenedores comparten `dokploy-network` y el DNS
de Docker resuelve por nombre de servicio en todas las redes: un servicio
llamado `backend` podría hacer que el nginx de otra aplicación le hable a esta
API, o al revés. **No renombres nada quitándole el prefijo.**

## 1. Base de datos

Crear en Dokploy un servicio **PostgreSQL 16** (Databases → PostgreSQL). Anotar
el nombre que Dokploy le asigna (algo como `xtrem-postgresql-a1b2c3`): ése es el
host, alcanzable desde `dokploy-network`.

Este repo **no** define un servicio de base de datos: el estado no debe vivir
dentro del stack de la aplicación.

## 2. Crear la aplicación

Dokploy → **Create Service → Compose**

| Campo | Valor |
|---|---|
| Provider | GitHub (o Git) |
| Repositorio | `pckernelsac/xtrem` |
| Rama | `main` |
| Compose Path | `./docker-compose.dokploy.yml` |

## 3. Variables (App → Environment)

Los valores reales **sólo van aquí**, nunca al repositorio, que es público.

```env
APP_DOMAIN=erp.tudominio.com
DATABASE_URL=postgresql://usuario:clave@xtrem-postgresql-a1b2c3:5432/zonaxtrema
SECRET_KEY=<openssl rand -hex 32>
TIMEZONE=America/Lima

# Sólo en el PRIMER deploy: crea permisos, roles y el administrador.
# La contraseña se imprime una vez en el log del contenedor. Después, false.
RUN_SEED=true
ADMIN_EMAIL=admin@tudominio.com
ADMIN_NAME=Administrador

# Facturación electrónica. Sin token: modo simulación, SIN validez ante SUNAT.
FACTPRO_TOKEN=
FACTPRO_CONSULTAS_TOKEN=
EMISOR_RUC=
EMISOR_RAZON_SOCIAL=
```

El dominio lo enruta Traefik con las labels del compose: no hace falta tocar la
pestaña *Domains*. Sí hace falta que el DNS del dominio apunte al servidor antes
del deploy, o Let's Encrypt no podrá emitir el certificado.

## 4. Deploy

Mirar el log en este orden:

1. **Clone** — que el commit sea el que esperas.
2. **Build** — si sale todo `CACHED` con código nuevo, el clone no se actualizó
   (ver *Problemas* abajo).
3. **Arranque del backend** — debe verse:
   `Esperando a Postgres…` → `Aplicando migraciones…` → `Arrancando API…`.
4. Si `RUN_SEED=true`, buscar en el log la línea `>>> CONTRASEÑA GENERADA:`
   y guardarla. **Después poner `RUN_SEED=false` y redeployar.**

## 5. Verificar sin fiarse de la interfaz

```bash
curl -sI https://TU_DOMINIO | grep -iE 'HTTP|cache-control'
curl -s  https://TU_DOMINIO/health          # {"status":"ok","environment":"production"}
curl -s -o /dev/null -w '%{http_code}\n' https://TU_DOMINIO/caja   # 200: ruta SPA
```

Comprobación de que el proxy apunta a **este** backend y no al de otro stack
—usa una ruta que sólo existe aquí—:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://TU_DOMINIO/api/v1/caja/sesiones
# 401 = correcto (pide autenticación, luego es nuestra API)
# 404 = está respondiendo otra aplicación
```

## Problemas frecuentes

**Sirve código viejo tras el deploy.** El clone vive en
`/etc/dokploy/compose/<app>/code`. Por SSH:

```bash
sudo git -C /etc/dokploy/compose/<app>/code log -1 --oneline
sudo git -C /etc/dokploy/compose/<app>/code fetch origin
sudo git -C /etc/dokploy/compose/<app>/code reset --hard origin/main
```

y redeployar.

**Rebuild manual** (el `.env` de la interfaz está en ese directorio y compose lo
lee solo):

```bash
cd /etc/dokploy/compose/<app>/code
sudo docker compose -f docker-compose.dokploy.yml -p <appName> build --no-cache
sudo docker compose -f docker-compose.dokploy.yml -p <appName> up -d
```

**El dominio responde otra aplicación.** Buscar routers duplicados y servicios
con nombres genéricos en la red compartida:

```bash
sudo docker ps --format '{{.Names}}'
sudo docker network inspect dokploy-network | grep -i name
```

**El navegador muestra la versión vieja.** El `index.html` se sirve con
`no-store` y los assets con `immutable`; si aun así pasa, es caché de un CDN o
proxy intermedio, no de la aplicación.

## Después del primer deploy

- [ ] `RUN_SEED=false`
- [ ] Cambiar la contraseña del administrador desde la aplicación
- [ ] `PUBLIC_BASE_URL` con el dominio real (lo hace el compose a partir de
      `APP_DOMAIN`), o los enlaces de WhatsApp no abrirán desde el celular
- [ ] Para facturar de verdad: cargar el certificado digital en FactPro y pasar
      la cuenta de demo a producción
