# Operations runbook

This runbook is deliberately small enough for one VPS operator. RomanPics is a
discovery layer: authoritative originals remain with NASA, STScI, or IPAC, and
generated previews can be rebuilt.

## Service objectives

- Normal catalog reads should remain available when one upstream source fails.
- A failed sync records a visible source-status error and retries individual
  records; it does not delete the last good catalog.
- No routine job downloads L1/L2 detector products or retains a fetched science
  original after derivative generation.
- Generated preview paths are content-addressed and can be discarded/rebuilt.
- The weekly link report should keep at least 95% of public source links valid.

## Daily checks

1. `GET /healthz` reports the API process and database connection separately.
2. `GET /v1/sources/status` shows the latest success, record count, and error for
   every adapter.
3. The job queue has no repeatedly failing job and its oldest ready job is less
   than one poll interval old.
4. Disk usage for PostgreSQL and the preview directory remains below the host's
   warning threshold.

Run durable catalog checks through the migration-owner operator container so the
public API never receives queue-write privileges:

```bash
docker compose --env-file /etc/romanpics/romanpics.env \
  run --rm operator enqueue-link-check
docker compose --profile worker --env-file /etc/romanpics/romanpics.env \
  up -d worker
```

The worker records every target result in `link_check`, including policy or
upstream failures. Alert on failed queue jobs, repeated link failures, and a
queue that stops draining; do not rely only on the weekly portable-catalog
workflow.

After correcting the underlying cause of terminal jobs, requeue a bounded batch
without changing their deduplication identities:

```bash
docker compose --env-file /etc/romanpics/romanpics.env \
  run --rm operator retry-failed-jobs --job-type embed --limit 100
```

## Database privilege check

After every migration, `db-grants` removes stale runtime privileges and applies
the checked-in allowlist. CI verifies the same boundary. For an on-host audit,
run this as the bootstrap login inside the PostgreSQL container and require a
single `t` result:

```bash
docker compose --env-file /etc/romanpics/romanpics.env exec -T postgres \
  sh -ec 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At' <<'SQL'
SELECT
  NOT has_schema_privilege('romanpics_api', 'public', 'CREATE')
  AND has_table_privilege('romanpics_api', 'gallery_item', 'SELECT')
  AND NOT has_column_privilege('romanpics_api', 'gallery_item', 'title', 'UPDATE')
  AND has_table_privilege('romanpics_api', 'vote_event', 'INSERT')
  AND NOT has_table_privilege('romanpics_api', 'vote_event', 'SELECT')
  AND has_column_privilege('romanpics_worker', 'jobs', 'status', 'UPDATE')
  AND has_table_privilege('romanpics_worker', 'cluster', 'INSERT')
  AND has_table_privilege('romanpics_worker', 'link_check', 'INSERT')
  AND has_column_privilege(
    'romanpics_worker', 'gallery_item', 'editorial_state', 'UPDATE'
  )
  AND NOT has_column_privilege(
    'romanpics_worker', 'gallery_item', 'title', 'UPDATE'
  );
SQL
```

When role names differ from the defaults, substitute the configured names. Treat
an unexpected privilege as a release blocker. Never give the public API or worker
the bootstrap or migration secret to work around a grant failure; update the
checked-in allowlist to match a reviewed code path.

## Sync and reconciliation

Incremental source syncs overlap their watermark by 48 hours and upsert by
source plus external ID. Run a full reconciliation weekly. Never interpret an
empty or failed upstream response as permission to delete records. Mark records
inactive only after a successful complete listing confirms their absence.

Prompt Roman products may be overwritten or superseded. Preserve the stable
RomanPics item ID, raw source ID, processing version, checksums/ETags, and a
supersession link. Migrate a gallery item to a preserved data-release product
without moving its votes or public URL.

## Backup and restore

Back up PostgreSQL daily with encrypted, off-host retention. The minimum restore
drill is quarterly:

1. Restore the latest dump into a new, isolated database.
2. Run migrations and the API smoke suite against the restored database.
3. Compare source, item, vote, collection, and active-job counts.
4. Rebuild a sample generated preview from its recorded recipe.
5. Record duration and any manual steps; a backup is not accepted until this
   drill succeeds.

Do not back up remote original image bytes. Backing up generated previews is
optional because they are reproducible; preserving their recipes is mandatory.

## Incident behavior

- **Provider outage:** pause only that adapter, keep stale records visible, and
  show the last successful sync on `/status`.
- **Broken preview:** fall back to another official rendition or a text-first
  card. Do not proxy an arbitrary replacement URL.
- **Suspected vote abuse:** rotate the daily IP-prefix HMAC key, tighten target
  rate limits, and challenge suspicious actors without publishing IP data.
- **Database incident:** put mutations in maintenance mode, keep a cached/static
  catalog readable, restore to a new database, then switch the internal URL.
- **Compromised secret:** rotate it outside Git, invalidate visitor cookies if
  the cookie-signing secret changed, and review append-only vote events.

## Release smoke test

Before promotion, verify the home page, a detail page, a group, a collection,
the status page, RSS/Atom, the embed route, OpenAPI output, one vote plus undo,
and one dry-run source sync. Confirm security headers, responsive image sizing,
keyboard focus, and a fallback state with the API intentionally unavailable.
