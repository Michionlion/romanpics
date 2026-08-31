#!/bin/sh
set -eu

PGPASSWORD="$(tr -d '\r\n' < /run/secrets/postgres_migration_password)"
if [ -z "$PGPASSWORD" ]; then
  echo "empty database secret: /run/secrets/postgres_migration_password" >&2
  exit 1
fi
export PGPASSWORD

exec psql \
  --host postgres \
  --username "$POSTGRES_MIGRATION_USER" \
  --dbname "$POSTGRES_DB" \
  --set db_name="$POSTGRES_DB" \
  --set api_user="$POSTGRES_API_USER" \
  --set worker_user="$POSTGRES_WORKER_USER" \
  --file /postgres-bootstrap/apply-grants.sql
