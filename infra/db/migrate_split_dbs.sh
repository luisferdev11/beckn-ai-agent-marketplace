#!/bin/bash
# migrate_split_dbs.sh — Migrates data from the monolithic beckn_ai_marketplace
# database to 3 domain-separated databases.
#
# Run inside the postgres container:
#   docker compose exec -T postgres bash /docker-entrypoint-initdb.d/migrate_split_dbs.sh
#
# Safe to run multiple times (uses ON CONFLICT / IF NOT EXISTS).
set -e

OLD_DB="${POSTGRES_DB:-beckn_ai_marketplace}"
CATALOG_DB="${DB_NAME_CATALOG:-beckn_catalog}"
TRANSACTIONS_DB="${DB_NAME_TRANSACTIONS:-beckn_transactions}"
METRICS_DB="${DB_NAME_METRICS:-beckn_metrics}"
PG_USER="${POSTGRES_USER:-postgres}"

echo "=== Migrating from '$OLD_DB' to domain databases ==="
echo "  Catalog:      $CATALOG_DB"
echo "  Transactions: $TRANSACTIONS_DB"
echo "  Metrics:      $METRICS_DB"

# ── 1. Create databases if they don't exist ─────────────────
for db in "$CATALOG_DB" "$TRANSACTIONS_DB" "$METRICS_DB"; do
    if psql -U "$PG_USER" -tc "SELECT 1 FROM pg_database WHERE datname = '$db'" | grep -q 1; then
        echo "  Database '$db' already exists"
    else
        psql -U "$PG_USER" -c "CREATE DATABASE \"$db\""
        echo "  Created database '$db'"
    fi
done

# ── 2. Create schemas in new databases ──────────────────────
MIGRATIONS_DIR="$(dirname "$0")/migrations"
# Handle both local and container paths
if [ -d "$MIGRATIONS_DIR" ]; then
    INIT_DIR="$MIGRATIONS_DIR"
elif [ -d "/docker-entrypoint-initdb.d/migrations" ]; then
    INIT_DIR="/docker-entrypoint-initdb.d/migrations"
else
    echo "ERROR: Cannot find migrations directory"
    exit 1
fi

echo "  Applying schemas..."
psql -U "$PG_USER" -d "$CATALOG_DB"      -f "$INIT_DIR/init_catalog.sql"      2>&1 | grep -v "already exists" || true
psql -U "$PG_USER" -d "$TRANSACTIONS_DB" -f "$INIT_DIR/init_transactions.sql" 2>&1 | grep -v "already exists" || true
psql -U "$PG_USER" -d "$METRICS_DB"      -f "$INIT_DIR/init_metrics.sql"      2>&1 | grep -v "already exists" || true
echo "  Schemas applied"

# ── 3. Enable dblink for cross-database data copy ──────────
for db in "$CATALOG_DB" "$TRANSACTIONS_DB" "$METRICS_DB"; do
    psql -U "$PG_USER" -d "$db" -c "CREATE EXTENSION IF NOT EXISTS dblink" 2>/dev/null
done

CONN="dbname=$OLD_DB user=$PG_USER"

# ── 4. Copy data: Catalog DB ───────────────────────────────
echo "  Copying catalog data..."

# categories
psql -U "$PG_USER" -d "$CATALOG_DB" <<SQL
INSERT INTO categories (id, name, display_name, description, is_active, created_at)
SELECT * FROM dblink('$CONN',
    'SELECT id, name, display_name, description, is_active, created_at FROM categories'
) AS t(id INTEGER, name VARCHAR(100), display_name JSONB, description TEXT, is_active BOOLEAN, created_at TIMESTAMPTZ)
ON CONFLICT (id) DO NOTHING;
SELECT setval('categories_id_seq', COALESCE((SELECT MAX(id) FROM categories), 1));
SQL

# providers
psql -U "$PG_USER" -d "$CATALOG_DB" <<SQL
INSERT INTO providers (id, subscriber_id, bpp_uri, public_key, organization, integration_mode, status, created_at, updated_at)
SELECT * FROM dblink('$CONN',
    'SELECT id, subscriber_id, bpp_uri, public_key, organization,
            COALESCE(integration_mode, ''external''), status, created_at, updated_at
     FROM providers'
) AS t(id INTEGER, subscriber_id TEXT, bpp_uri TEXT, public_key TEXT, organization JSONB, integration_mode VARCHAR(20), status VARCHAR(20), created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)
ON CONFLICT (id) DO NOTHING;
SELECT setval('providers_id_seq', COALESCE((SELECT MAX(id) FROM providers), 1));
SQL

# agents (excluding removed columns: credentials, llm_provider, llm_model, system_prompt, temperature)
psql -U "$PG_USER" -d "$CATALOG_DB" <<SQL
INSERT INTO agents (id, provider_id, category_id, beckn_id, agentfacts_id, agent_urn, label,
    agent_name, description, version, access_point_url, interaction_type,
    capabilities, skills, input_schema, output_schema, pricing_model, sla,
    jurisdiction, endpoints, status, created_at, updated_at)
SELECT * FROM dblink('$CONN',
    'SELECT id, provider_id, category_id, beckn_id, agentfacts_id, agent_urn, label,
            agent_name, description, version,
            COALESCE(access_point_url, ''http://agents:3004''),
            interaction_type, capabilities, skills, input_schema, output_schema,
            pricing_model, sla, jurisdiction, endpoints, status, created_at, updated_at
     FROM agents'
) AS t(id INTEGER, provider_id INTEGER, category_id INTEGER, beckn_id TEXT, agentfacts_id TEXT,
       agent_urn TEXT, label TEXT, agent_name JSONB, description TEXT, version VARCHAR(20),
       access_point_url TEXT, interaction_type VARCHAR(20), capabilities JSONB, skills JSONB,
       input_schema JSONB, output_schema JSONB, pricing_model JSONB, sla JSONB,
       jurisdiction VARCHAR(10), endpoints JSONB, status VARCHAR(20),
       created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)
ON CONFLICT (id) DO NOTHING;
SELECT setval('agents_id_seq', COALESCE((SELECT MAX(id) FROM agents), 1));
SQL

# users
psql -U "$PG_USER" -d "$CATALOG_DB" <<SQL
INSERT INTO users (id, email, password_hash, role, subscription_status, provider_id, created_at, updated_at)
SELECT * FROM dblink('$CONN',
    'SELECT id, email, password_hash, role, subscription_status, provider_id, created_at, updated_at
     FROM users'
) AS t(id UUID, email VARCHAR(255), password_hash VARCHAR(255), role VARCHAR(20),
       subscription_status VARCHAR(20), provider_id INTEGER, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)
ON CONFLICT (id) DO NOTHING;
SQL

echo "  Catalog data copied"

# ── 5. Copy data: Transactions DB ──────────────────────────
echo "  Copying transaction data..."

# contracts
psql -U "$PG_USER" -d "$TRANSACTIONS_DB" <<SQL
INSERT INTO contracts (id, contract_code, transaction_id, message_id, agent_id, provider_id,
    bap_id, bpp_id, status, commitments, consideration, performance, settlements, participants,
    execution_id, total_amount, currency, created_at, initialized_at, confirmed_at, completed_at)
SELECT * FROM dblink('$CONN',
    'SELECT id, contract_code, transaction_id, message_id, agent_id, provider_id,
            bap_id, bpp_id, status, commitments, consideration, performance, settlements,
            participants, execution_id, total_amount, currency, created_at,
            initialized_at, confirmed_at, completed_at
     FROM contracts'
) AS t(id INTEGER, contract_code TEXT, transaction_id TEXT, message_id TEXT,
       agent_id INTEGER, provider_id INTEGER, bap_id TEXT, bpp_id TEXT,
       status VARCHAR(20), commitments JSONB, consideration JSONB, performance JSONB,
       settlements JSONB, participants JSONB, execution_id TEXT,
       total_amount NUMERIC(12,2), currency CHAR(3), created_at TIMESTAMPTZ,
       initialized_at TIMESTAMPTZ, confirmed_at TIMESTAMPTZ, completed_at TIMESTAMPTZ)
ON CONFLICT (id) DO NOTHING;
SELECT setval('contracts_id_seq', COALESCE((SELECT MAX(id) FROM contracts), 1));
SQL

# callbacks
psql -U "$PG_USER" -d "$TRANSACTIONS_DB" <<SQL
INSERT INTO callbacks (id, transaction_id, action, context, message, received_at)
SELECT * FROM dblink('$CONN',
    'SELECT id, transaction_id, action, context, message, received_at FROM callbacks'
) AS t(id INTEGER, transaction_id TEXT, action VARCHAR(30), context JSONB, message JSONB, received_at TIMESTAMPTZ)
ON CONFLICT (id) DO NOTHING;
SELECT setval('callbacks_id_seq', COALESCE((SELECT MAX(id) FROM callbacks), 1));
SQL

# executions
psql -U "$PG_USER" -d "$TRANSACTIONS_DB" <<SQL
INSERT INTO executions (id, execution_code, contract_id, agent_id, status, input_payload,
    result, error_message, latency_ms, tokens_input, tokens_output, model_used,
    timeout_ms, started_at, completed_at)
SELECT * FROM dblink('$CONN',
    'SELECT id, execution_code, contract_id, agent_id, status, input_payload,
            result, error_message, latency_ms, tokens_input, tokens_output, model_used,
            timeout_ms, started_at, completed_at
     FROM executions'
) AS t(id INTEGER, execution_code TEXT, contract_id INTEGER, agent_id INTEGER,
       status VARCHAR(20), input_payload JSONB, result JSONB, error_message TEXT,
       latency_ms INTEGER, tokens_input INTEGER, tokens_output INTEGER, model_used TEXT,
       timeout_ms INTEGER, started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ)
ON CONFLICT (id) DO NOTHING;
SELECT setval('executions_id_seq', COALESCE((SELECT MAX(id) FROM executions), 1));
SQL

echo "  Transaction data copied"

# ── 6. Copy data: Metrics DB ───────────────────────────────
echo "  Copying metrics data..."

psql -U "$PG_USER" -d "$METRICS_DB" <<SQL
INSERT INTO agent_stats (id, agent_id, total_queries, unique_users, last_used_at, week_queries, recorded_at)
SELECT * FROM dblink('$CONN',
    'SELECT id, agent_id, total_queries, unique_users, last_used_at, week_queries, recorded_at
     FROM agent_stats'
) AS t(id INTEGER, agent_id INTEGER, total_queries INTEGER, unique_users INTEGER,
       last_used_at TIMESTAMPTZ, week_queries INTEGER, recorded_at DATE)
ON CONFLICT (id) DO NOTHING;
SELECT setval('agent_stats_id_seq', COALESCE((SELECT MAX(id) FROM agent_stats), 1));
SQL

echo "  Metrics data copied"

echo ""
echo "=== Migration complete ==="
echo "Old database '$OLD_DB' is untouched — you can drop it when ready:"
echo "  psql -U $PG_USER -c \"DROP DATABASE $OLD_DB\""
