#!/usr/bin/env bash
# Render start command. With LITESTREAM_BUCKET set, the database is restored from
# the replica before start-up and every change is streamed back while the API runs.
# Without it the database lives on the temporary disk and resets on restart.
set -euo pipefail

APP="python -m uvicorn app.main:application --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}"
LITESTREAM=./bin/litestream
CONFIG=backend/litestream.yml

prepare_db() {
  python -m backend.migrate up
  # Exit code 2 means the data is already there, which is the normal case after a restore.
  python -m backend.seed || true
}

if [ -n "${LITESTREAM_BUCKET:-}" ] && [ -x "$LITESTREAM" ]; then
  export SQLITE_WAL=1
  echo "Restoring database from replica (if one exists)..."
  "$LITESTREAM" restore -config "$CONFIG" -if-db-not-exists -if-replica-exists "$DATABASE_PATH"
  prepare_db
  exec "$LITESTREAM" replicate -config "$CONFIG" -exec "$APP"
else
  echo "LITESTREAM_BUCKET not set: the database is temporary and resets on restart."
  prepare_db
  exec $APP
fi
