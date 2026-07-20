#!/usr/bin/env bash
#
# Restaura un backup de Zona Xtrema.
#
# Uso:  ./scripts/restore.sh backups/zonaxtrema_20260719_020000.sql.gz
#
# ¡DESTRUCTIVO! Reemplaza el contenido de la base actual por el del backup.
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"
FILE="${1:-}"

if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
  echo "Uso: $0 <archivo.sql.gz>" >&2
  echo "Backups disponibles:" >&2
  ls -1t "$DIR"/backups/zonaxtrema_*.sql.gz 2>/dev/null || echo "  (ninguno)" >&2
  exit 1
fi

[ -f "$DIR/.env" ] && set -a && . "$DIR/.env" && set +a
USER_DB="${POSTGRES_USER:-zonaxtrema}"
NAME_DB="${POSTGRES_DB:-zonaxtrema}"

echo "Vas a RESTAURAR '$FILE' sobre la base '$NAME_DB'."
echo "Esto reemplaza los datos actuales. Escribe 'restaurar' para continuar:"
read -r confirm
[ "$confirm" = "restaurar" ] || { echo "Cancelado."; exit 1; }

gunzip -c "$FILE" | docker compose -f "$DIR/docker-compose.yml" exec -T zx_db \
  psql -U "$USER_DB" -d "$NAME_DB" -q

echo "Restauración completada. Reinicia la API: docker compose restart zx_api"
