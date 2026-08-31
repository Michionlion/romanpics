#!/bin/sh
set -eu

db_password="$(tr -d '\r\n' < /run/secrets/postgres_migration_password)"
visitor_secret="$(tr -d '\r\n' < /run/secrets/visitor_signing_secret)"
if [ -z "$db_password" ] || [ -z "$visitor_secret" ]; then
  echo "operator database/signing secret is empty" >&2
  exit 1
fi

export DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${db_password}@postgres:5432/${POSTGRES_DB}"
export VISITOR_SIGNING_SECRET="$visitor_secret"
runtime_uid="$(id -u romanpics)"
runtime_gid="$(id -g romanpics)"
exec setpriv --reuid="$runtime_uid" --regid="$runtime_gid" \
  --clear-groups --no-new-privs romanpics "$@"
