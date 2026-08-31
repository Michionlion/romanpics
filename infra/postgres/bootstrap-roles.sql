\set ON_ERROR_STOP on

-- Passwords arrive through the one-shot container environment, not argv or SQL
-- files. format(%I/%L) safely quotes configurable role names and secret values.
\getenv migration_password ROMANPICS_MIGRATION_PASSWORD
\getenv api_password ROMANPICS_API_PASSWORD
\getenv worker_password ROMANPICS_WORKER_PASSWORD

SELECT format('CREATE ROLE %I LOGIN', :'migration_user')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'migration_user')
\gexec
SELECT format('CREATE ROLE %I LOGIN', :'api_user')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'api_user')
\gexec
SELECT format('CREATE ROLE %I LOGIN', :'worker_user')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'worker_user')
\gexec

SELECT format(
  'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
  :'migration_user', :'migration_password'
) \gexec
SELECT format(
  'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
  :'api_user', :'api_password'
) \gexec
SELECT format(
  'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
  :'worker_user', :'worker_password'
) \gexec

-- `public` must be first so unqualified Alembic DDL targets the owned schema.
-- Runtime roles cannot create there, preventing object-shadowing attacks.
SELECT format('ALTER ROLE %I SET search_path = public, pg_catalog', :'migration_user') \gexec
SELECT format('ALTER ROLE %I SET search_path = public, pg_catalog', :'api_user') \gexec
SELECT format('ALTER ROLE %I SET search_path = public, pg_catalog', :'worker_user') \gexec
SELECT format('ALTER ROLE %I SET statement_timeout = %L', :'api_user', '15s') \gexec
SELECT format('ALTER ROLE %I SET statement_timeout = %L', :'worker_user', '60s') \gexec

-- This runs before Alembic so the migration login owns every application
-- object. Repeating it is safe and also repairs database/schema ownership.
SELECT format('ALTER DATABASE %I OWNER TO %I', :'db_name', :'migration_user') \gexec
\connect :db_name
-- Adopt relations from the legacy single-role deployment without reassigning
-- cluster-wide objects (which a broad REASSIGN OWNED would also touch).
SELECT format(
  'ALTER %s %I.%I OWNER TO %I',
  CASE c.relkind WHEN 'S' THEN 'SEQUENCE' ELSE 'TABLE' END,
  n.nspname,
  c.relname,
  :'migration_user'
)
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
JOIN pg_roles AS owner ON owner.oid = c.relowner
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'p', 'S')
  AND owner.rolname = :'bootstrap_user'
\gexec
SELECT format('ALTER SCHEMA public OWNER TO %I', :'migration_user') \gexec

REVOKE CONNECT ON DATABASE :"db_name" FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'db_name', :'migration_user') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'db_name', :'api_user') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'db_name', :'worker_user') \gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'api_user') \gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'worker_user') \gexec

-- The worker serializes global cluster replacement with this one transaction
-- lock. Remove the default PUBLIC grant for the exact overload it invokes.
REVOKE EXECUTE ON FUNCTION pg_catalog.pg_advisory_xact_lock(bigint) FROM PUBLIC;
SELECT format(
  'GRANT EXECUTE ON FUNCTION pg_catalog.pg_advisory_xact_lock(bigint) TO %I',
  :'worker_user'
) \gexec
