#!/bin/sh
set -e

echo "Running migrations..."
attempt=1
until uv run --no-sync alembic -c alembic.ini upgrade head; do
  attempt=$((attempt + 1))
  if [ "$attempt" -gt 10 ]; then
    echo "Migrations failed after $((attempt - 1)) attempts, exiting."
    exit 1
  fi
  echo "Migration failed, retrying in 3s... (attempt $attempt)"
  sleep 3
done

echo "Starting API..."
exec uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000
