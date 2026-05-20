#!/usr/bin/env bash
# Entrypoint shared by every container role.
# - waits for Postgres
# - the `web` role additionally runs migrations + collectstatic (run once)
set -euo pipefail

echo "⏳ Waiting for PostgreSQL at ${POSTGRES_HOST}:${POSTGRES_PORT}…"
until python -c "
import os, socket, sys
s = socket.socket()
s.settimeout(2)
try:
    s.connect((os.environ['POSTGRES_HOST'], int(os.environ['POSTGRES_PORT'])))
except Exception:
    sys.exit(1)
" 2>/dev/null; do
  sleep 1
done
echo "✅ PostgreSQL is up."

# Only the primary web container should run migrations/collectstatic so the
# other roles (celery, beat, mqtt bridge) don't race on them.
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  echo "▶ Applying migrations…"
  python manage.py migrate --noinput
  echo "▶ Collecting static files…"
  python manage.py collectstatic --noinput
fi

exec "$@"
