# RomanPics VPS integration

This bundle runs only the stateful backend on the VPS: PostgreSQL, one-shot role
bootstrap and grants, an Alembic migration, an idempotent catalog seed, FastAPI,
and the optional worker profile. The frontend remains on a static/free host and
points `NEXT_PUBLIC_API_BASE` at the VPS API origin. PostgreSQL has no host port;
the API is available on loopback for diagnostics and on one purpose-built Docker
edge network for the existing Nginx container.

## Database trust boundaries

Compose provisions four distinct logins. `db-bootstrap` is the only application
container that receives the cluster bootstrap password, and it exits before the
public API starts.

| Login | Used by | Intended database access |
| --- | --- | --- |
| `romanpics` (bootstrap default) | PostgreSQL initialization, `db-bootstrap` | Cluster superuser; never mounted into API, migration, seed, or worker |
| `romanpics_migrator` | Alembic, seed, reviewed operator commands | Owns the application database/schema/objects |
| `romanpics_api` | Public FastAPI process | Catalog reads; insert/delete active votes; append vote events; maintain vote totals |
| `romanpics_worker` | Optional worker | Resolver reads; lease/update jobs; persist render, embedding, cluster, and link-check results |

`infra/postgres/bootstrap-roles.sql` creates or repairs roles and ownership before
Alembic. `apply-grants.sql` first removes all API/worker table and sequence grants,
then reapplies the explicit allowlist after every migration. A migration that
adds a runtime table or a new write path must update that file in the same pull
request. Runtime roles receive no schema creation, database creation, role
creation, replication, superuser, or row-security bypass capability.

The bootstrap login keeps the original `romanpics` default so an existing volume
remains accessible; its old `public`-schema tables and sequences are adopted by
the migration owner automatically. Back up the database before this first
ownership transition. If the original deployment used a custom `POSTGRES_USER`,
set `POSTGRES_BOOTSTRAP_USER` to that exact existing role. PostgreSQL ignores new
initialization variables on a non-empty data directory.

## Why the worker profile remains optional

The worker is available with `--profile worker`. It leases the canonical
PostgreSQL queue with `SKIP LOCKED`, validates the shared jobs-v1 payloads, and
persists all four job result types transactionally. Its own generated-preview
origin is read directly from the mounted preview volume; external fetches still
use the reviewed host policy. Enable the profile when its schedule and alerts
are ready. Every future worker write path must add only its exact new DML
privileges to `infra/postgres/apply-grants.sql`.

Reviewed operator CLI commands run through the one-shot `operator` service with
the migration-owner credential; the browser-facing API never receives that
secret. For example:

```bash
docker compose --env-file /etc/romanpics/romanpics.env \
  run --rm operator enqueue-link-check
docker compose --env-file /etc/romanpics/romanpics.env \
  run --rm operator retry-failed-jobs --limit 100
```

## First deployment

1. Create the external resources shared with Nginx:

   ```bash
   docker network inspect romanpics-edge >/dev/null 2>&1 || \
     docker network create romanpics-edge
   docker volume inspect romanpics-previews >/dev/null 2>&1 || \
     docker volume create romanpics-previews
   ```

2. Follow `infra/secrets/README.md`. Copy `.env.example` to a root-readable file
   outside Git, replace the example domains, and keep `COOKIE_SECURE=true`.
   Use `COOKIE_SAMESITE=none` only when frontend and API are genuinely cross-site;
   that setting requires HTTPS. Comma-separate multiple exact origins—never use
   `*` with credentialed voting requests.

3. Validate and start the API. The dependency chain requires a healthy database,
   successful role bootstrap, migration, privilege reconciliation, and seed
   before FastAPI starts:

   ```bash
   docker compose --env-file /etc/romanpics/romanpics.env config --quiet
   docker compose --env-file /etc/romanpics/romanpics.env up -d --build --wait api
   curl --fail http://127.0.0.1:8080/readyz
   ```

   `seed` is safe to rerun. Migration and seed containers intentionally stop with
   exit code zero; they are not failed services.

## Connect the existing Dockerized Nginx

The neighboring website project mounts `nginx/conf.d` read-only into its Nginx
container and already uses Docker DNS at `127.0.0.11`. It is not a host-installed
Nginx and cannot reach a loopback-bound container through its own `127.0.0.1`.
The supplied override attaches it to `romanpics-edge`; the API advertises the
stable network alias `romanpics-api`.

Use the HTTP-only template for initial certificate issuance. After the certificate
exists, copy the TLS template and its include file, replacing the hostname:

```bash
sudo install -m 644 infra/nginx/romanpics-proxy-headers.inc \
  /home/saejin/projects/website/nginx/conf.d/romanpics-proxy-headers.inc
sudo install -m 644 infra/nginx/romanpics-api.conf.template \
  /home/saejin/projects/website/nginx/conf.d/romanpics-api.conf
cd /home/saejin/projects/website
docker compose -f docker-compose.yml \
  -f /path/to/romanpics/infra/nginx/website.compose.override.yml config --quiet
docker compose -f docker-compose.yml \
  -f /path/to/romanpics/infra/nginx/website.compose.override.yml up -d nginx
docker compose exec nginx nginx -t
docker compose exec nginx nginx -s reload
```

Always include the override in later website Compose commands, or copy its one
network and one volume mount into that project's base Compose file. The preview
volume is deliberately empty today; Nginx is ready to serve future
content-addressed WebP files at `/previews/` without exposing originals.

The API process trusts forwarded headers because only loopback and the isolated
edge network can reach it. Do not publish container port 8000 on `0.0.0.0` or
attach untrusted workloads to `romanpics-edge`.

Compose briefly starts each API-image container as root with only
`DAC_READ_SEARCH`, `SETUID`, and `SETGID` capabilities so it can read host files
that remain mode `0600`. Its fixed bootstrap then drops to the image's
`romanpics` UID, clears supplementary groups, and enables `no_new_privs` before
running Alembic, the seeder, or Uvicorn. Do not replace that fixed command with
user-controlled shell text.

## Operations and rollback

- Inspect: `docker compose --env-file /etc/romanpics/romanpics.env ps`
- Logs: `docker compose --env-file /etc/romanpics/romanpics.env logs api seed db-grants migrate db-bootstrap postgres`
- Reconcile roles/passwords: `docker compose --env-file /etc/romanpics/romanpics.env run --rm db-bootstrap`
- Rerun migration: `docker compose --env-file /etc/romanpics/romanpics.env run --rm migrate`
- Reapply runtime grants: `docker compose --env-file /etc/romanpics/romanpics.env run --rm db-grants`
- Rerun seed: `docker compose --env-file /etc/romanpics/romanpics.env run --rm seed`
- Stop app containers: `docker compose --env-file /etc/romanpics/romanpics.env down`

Do not add `--volumes` in production: that deletes the Compose-managed PostgreSQL
volume. Take a tested logical backup before upgrades. A code rollback should use
the previous image tag and leave the database volume intact; database downgrades
require a separately reviewed migration plan.
