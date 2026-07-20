#!/bin/sh
# Arranque del backend en producción: esperar la base, migrar y servir.
#
# El host y el puerto se sacan de DATABASE_URL cuando existe (en Dokploy la
# base es un servicio aparte y su nombre no es "db"), y sólo si no está se cae
# a las piezas sueltas POSTGRES_* del compose local.
set -e

if [ -n "$DATABASE_URL" ]; then
    # postgresql://usuario:clave@HOST:PUERTO/base -> HOST y PUERTO
    sin_esquema=${DATABASE_URL#*://}
    autoridad=${sin_esquema#*@}      # descarta credenciales si las hay
    hostport=${autoridad%%/*}        # descarta /base y ?params
    DB_HOST=${hostport%%:*}
    DB_PORT=${hostport#*:}
    [ "$DB_PORT" = "$DB_HOST" ] && DB_PORT=5432   # no traía puerto explícito
else
    DB_HOST=${POSTGRES_HOST:-db}
    DB_PORT=${POSTGRES_PORT:-5432}
fi

echo "Esperando a Postgres en $DB_HOST:$DB_PORT ..."
intentos=0
until python -c "
import socket, sys
s = socket.socket()
s.settimeout(2)
try:
    s.connect(('$DB_HOST', int('$DB_PORT')))
except Exception:
    sys.exit(1)
" 2>/dev/null; do
    intentos=$((intentos + 1))
    if [ "$intentos" -ge 60 ]; then
        echo "ERROR: la base no respondió tras 60 intentos." >&2
        exit 1
    fi
    sleep 2
done
echo "Postgres disponible."

echo "Aplicando migraciones..."
alembic upgrade head

# El seed crea permisos, roles y el administrador. Es idempotente, pero se deja
# tras una bandera para no tocar producción en cada redeploy sin querer.
if [ "$RUN_SEED" = "true" ]; then
    echo "Ejecutando seed..."
    python -m app.db.seed
fi

echo "Arrancando API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
