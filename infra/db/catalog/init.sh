#!/bin/bash
set -e

echo "Running catalog migrations..."
for f in /docker-entrypoint-initdb.d/migrations/*.sql; do
    echo "  Applying: $(basename "$f")"
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$f"
done
echo "Catalog migrations applied."
