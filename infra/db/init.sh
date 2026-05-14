#!/bin/bash
set -e

CATALOG_DB="${DB_NAME_CATALOG:-beckn_catalog}"
TRANSACTIONS_DB="${DB_NAME_TRANSACTIONS:-beckn_transactions}"
METRICS_DB="${DB_NAME_METRICS:-beckn_metrics}"

echo "Creating domain databases..."
for db in "$CATALOG_DB" "$TRANSACTIONS_DB" "$METRICS_DB"; do
    psql -U "$POSTGRES_USER" -tc "SELECT 1 FROM pg_database WHERE datname = '$db'" | grep -q 1 \
        || psql -U "$POSTGRES_USER" -c "CREATE DATABASE \"$db\""
    echo "  Database '$db' ready"
done

echo "Applying init scripts..."
psql -U "$POSTGRES_USER" -d "$CATALOG_DB"      -f /docker-entrypoint-initdb.d/migrations/init_catalog.sql
psql -U "$POSTGRES_USER" -d "$TRANSACTIONS_DB"  -f /docker-entrypoint-initdb.d/migrations/init_transactions.sql
psql -U "$POSTGRES_USER" -d "$METRICS_DB"       -f /docker-entrypoint-initdb.d/migrations/init_metrics.sql

echo "All databases initialized."
