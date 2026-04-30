#!/bin/bash
set -e

echo "Running migrations..."
for f in /docker-entrypoint-initdb.d/migrations/*.sql; do
    echo "  Applying: $(basename "$f")"
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$f"
done
echo "All migrations applied."
