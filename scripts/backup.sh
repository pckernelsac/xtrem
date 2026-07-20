#!/usr/bin/env bash
#
# Backup de la base de datos de Zona Xtrema.
#
# Uso:   ./scripts/backup.sh [carpeta_destino]
# Cron:  0 2 * * *  cd /ruta/zonaxtrema && ./scripts/backup.sh >> backups/backup.log 2>&1
#
# Genera un dump comprimido y conserva los últimos 14. El dump usa
# --clean --if-exists, así que restaurarlo sobre una base existente la reemplaza.
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$DIR/backups}"
mkdir -p "$DEST"

# Carga POSTGRES_USER / POSTGRES_DB del .env si existe.
[ -f "$DIR/.env" ] && set -a && . "$DIR/.env" && set +a
USER_DB="${POSTGRES_USER:-zonaxtrema}"
NAME_DB="${POSTGRES_DB:-zonaxtrema}"

STAMP="$(date +%Y%m%d_%H%M%S)"
FILE="$DEST/zonaxtrema_$STAMP.sql.gz"

echo "[$(date +'%F %T')] Iniciando backup de '$NAME_DB'..."
docker compose -f "$DIR/docker-compose.yml" exec -T zx_db \
  pg_dump -U "$USER_DB" -d "$NAME_DB" --clean --if-exists \
  | gzip > "$FILE"

TAM="$(du -h "$FILE" | cut -f1)"
echo "[$(date +'%F %T')] Backup creado: $FILE ($TAM)"

# Retención: elimina los backups más allá de los 14 más recientes.
RETENER=14
sobran="$(ls -1t "$DEST"/zonaxtrema_*.sql.gz 2>/dev/null | tail -n "+$((RETENER + 1))" || true)"
if [ -n "$sobran" ]; then
  echo "$sobran" | xargs -r rm -f
  echo "[$(date +'%F %T')] Eliminados backups antiguos (se conservan $RETENER)."
fi
