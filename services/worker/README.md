# RomanPics worker prototype

This directory is a standalone, offline-first Python worker package intended to be
copied into `services/worker/` in RomanPics. It prepares the risky data-pipeline
pieces before Roman begins publishing flight science products:

- deterministic 320 px and 768 px WebP previews from FITS and ASDF arrays;
- documented, reproducible WFI filter-to-RGB recipes;
- temporary-product cleanup and content-addressed output names;
- opt-in remote fetching with URL, host, DNS, redirect, size, and MIME validation;
- SHA-256 and DCT perceptual hashes for duplicate detection;
- deterministic visual/metadata embeddings and optional OpenCLIP or SigLIP;
- content-class-partitioned cosine k-NN grouping with explicit product-family edges;
- stable cluster IDs, immutable versions, and split/merge/disappearance lineage;
- recorded MAST-shaped fixtures for prompt overwrite and final supersession behavior;
- backend-compatible SQLite and psycopg 3 PostgreSQL job stores with atomic
  `FOR UPDATE SKIP LOCKED` leases, heartbeats, recovery, retry, and dead-letter state.

The package does **not** ship or cache source imagery. Backend jobs carry catalog IDs,
never source URLs or filesystem paths. The worker verifies those IDs and relationships
against the catalog, applies the independent upstream allowlist, holds a downloaded
science product only inside a temporary directory, and removes it after rendering.

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
romanpics-worker --help
```

Render a local product:

```bash
romanpics-worker render sample.fits --output ./previews
```

Network access takes two deliberate switches: `--enable-network` and at least one
exact `--allow-host`. The default response limit is 64 MiB; a larger science product
must be approved for that job explicitly.

```bash
romanpics-worker render-url 'https://archive.stsci.edu/example.fits' \
  --output ./previews \
  --enable-network \
  --allow-host archive.stsci.edu
```

Create a local queue and submit a contract-valid job:

```bash
romanpics-worker init-db --database worker.sqlite3
romanpics-worker enqueue --database worker.sqlite3 render \
  '{"item_id":"11111111-1111-4111-8111-111111111111","product_id":"22222222-2222-4222-8222-222222222222","recipe":{"version":"v1"}}'
```

The SQLite database must contain the backend catalog tables for render/embed/cluster
or link-check execution. PostgreSQL is the deployment path:

```bash
romanpics-worker work \
  --database-url 'postgresql+psycopg://romanpics:secret@db/romanpics' \
  --forever \
  --enable-network \
  --allow-host archive.stsci.edu \
  --allow-host images-assets.nasa.gov \
  --preview-dir /previews \
  --preview-base-url https://img.romanpics.org
```

Workers heartbeat running jobs every 30 seconds and recover leases older than five
minutes on startup. `recover-leases` is available as a separate scheduled command.
Jobs at `max_attempts` become `failed`, the backend schema's dead-letter state.

Render completion is transactional and idempotent at the catalog boundary: it upserts
site-generated `Rendition` rows, publishes only an item that is still `draft` with
`metadata_json.publication_gate == "render"`, removes that gate, clears the exact
render-wait processing note, and deduplicates a follow-up embed job. A hidden or
manually ungated item receives its renditions but is never published. Embed completion
revalidates the item/source/checksum tuple and upserts the versioned `Embedding` row.

## Safety and operating assumptions

- Unit tests use generated arrays, local recorded metadata, and fake HTTP transports.
  They make no live DNS or network calls.
- `docs/job-contract.json` is the backend's jobs-v1 contract. Runtime validation
  rejects unknown job types, extra payload fields, malformed UUIDs, and stale checksums.
- Worker URL inputs are selected from related `archive_product`, `rendition`, and
  catalog link rows. Queue recipes and scopes cannot inject a URL.
- The default fetcher is disabled and has an empty host allowlist.
- Each redirect is revalidated and re-resolved. Any private, loopback, link-local,
  multicast, reserved, or otherwise non-global address is rejected.
- `application/octet-stream` is accepted because science archives commonly use it;
  the selected FITS/ASDF parser must still accept the downloaded bytes.
- The included HTTP transport validates DNS immediately before connecting but does
  not pin an IP into the TLS connection. Production should restrict hosts to trusted
  NASA/STScI domains and use an egress proxy that pins the validated resolution if a
  compromised allowlisted DNS zone is in scope.
- Original FITS/ASDF objects can be much larger than a free web host permits. Keep
  ingestion on the VPS, enforce per-job limits, and publish only generated previews.

See [rendering recipes](docs/color-recipes.md), [pipeline design](docs/pipeline.md),
and [PostgreSQL lease SQL](docs/postgres_jobs.sql).

Set `ROMANPICS_TEST_DATABASE_URL` to a disposable PostgreSQL database to enable the
opt-in test covering concurrent claims, recovery, render publication, embed enqueue,
selected-rendition hydration, and embedding persistence.
