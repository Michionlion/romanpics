#!/bin/sh
set -eu

read_secret() {
  value="$(tr -d '\r\n' < "$1")"
  if [ -z "$value" ]; then
    echo "empty database secret: $1" >&2
    exit 1
  fi
  printf '%s' "$value"
}

for required_name in \
  POSTGRES_DB \
  POSTGRES_BOOTSTRAP_USER \
  POSTGRES_MIGRATION_USER \
  POSTGRES_API_USER \
  POSTGRES_WORKER_USER
do
  eval "required_value=\${$required_name:-}"
  if [ -z "$required_value" ]; then
    echo "missing required setting: $required_name" >&2
    exit 1
  fi
done

if [ "$POSTGRES_BOOTSTRAP_USER" = "$POSTGRES_MIGRATION_USER" ] || \
   [ "$POSTGRES_BOOTSTRAP_USER" = "$POSTGRES_API_USER" ] || \
   [ "$POSTGRES_BOOTSTRAP_USER" = "$POSTGRES_WORKER_USER" ] || \
   [ "$POSTGRES_MIGRATION_USER" = "$POSTGRES_API_USER" ] || \
   [ "$POSTGRES_MIGRATION_USER" = "$POSTGRES_WORKER_USER" ] || \
   [ "$POSTGRES_API_USER" = "$POSTGRES_WORKER_USER" ]; then
  echo "database role names must be distinct" >&2
  exit 1
fi

PGPASSWORD="$(read_secret /run/secrets/postgres_bootstrap_password)"
ROMANPICS_MIGRATION_PASSWORD="$(
  read_secret /run/secrets/postgres_migration_password
)"
ROMANPICS_API_PASSWORD="$(read_secret /run/secrets/postgres_api_password)"
ROMANPICS_WORKER_PASSWORD="$(read_secret /run/secrets/postgres_worker_password)"
export PGPASSWORD
export ROMANPICS_MIGRATION_PASSWORD
export ROMANPICS_API_PASSWORD
export ROMANPICS_WORKER_PASSWORD

exec psql \
  --host postgres \
  --username "$POSTGRES_BOOTSTRAP_USER" \
  --dbname postgres \
  --set db_name="$POSTGRES_DB" \
  --set bootstrap_user="$POSTGRES_BOOTSTRAP_USER" \
  --set migration_user="$POSTGRES_MIGRATION_USER" \
  --set api_user="$POSTGRES_API_USER" \
  --set worker_user="$POSTGRES_WORKER_USER" \
  --file /postgres-bootstrap/bootstrap-roles.sql
