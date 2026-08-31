# RomanPics catalog API

This is the production-shaped API service for RomanPics. It indexes
metadata and official remote renditions; it never mirrors original science
products or exposes an arbitrary image proxy.

## Included

- FastAPI and SQLAlchemy 2, with PostgreSQL as the production database and
  SQLite compatibility for offline tests.
- Idempotent adapters for NASA Images, NASA SVS, a reviewed JSON manifest, and
  feature-gated MAST fixtures.
- Source/run health, canonical provenance, observations/products/renditions,
  tags, clusters, similarity edges, collections, and append-only vote events.
- Cursor-paginated public API matching the drift-checked RomanPics OpenAPI contract.
- Signed anonymous visitor cookies, one-active-vote constraints, origin checks,
  and replaceable rate-limit hooks.
- A PostgreSQL worker lease queue aligned to the `render`, `embed`, `cluster`,
  and `link-check` payloads in `docs/job-contract.json`.
- Offline fixtures, migration, CLI synchronization/direct-link-check commands,
  durable worker link-check enqueueing, and tests with no network dependency.

## Run locally

```bash
uv sync --locked --extra dev
uv run alembic upgrade head
uv run romanpics seed --manifest manifests/reviewed.json
uv run uvicorn romanpics_api.main:app --reload
uv run ruff check .
uv run pytest
uv run pip-audit --local
```

For a disposable SQLite demo:

```bash
export DATABASE_URL=sqlite:///./romanpics.db
export COOKIE_SECURE=false
uv run romanpics init-db
uv run romanpics sync reviewed_manifest --fixture manifests/reviewed.json
uv run romanpics enqueue-link-check
```

Canonical API routes are rooted at `/v1`; an edge may expose `/api/v1` by
stripping `/api`. Health probes are at `/healthz` and `/readyz`.

`GET /v1/surprise?mode=anything|galaxies|mission|calm|engineering` returns
exactly `{ "mode": "...", "item": { ...GalleryItem } }`. It is deliberately
`no-store`; deterministic catalog reads use ETags and honor `If-None-Match`.
Production should run migrations separately, use a strong signing secret, keep
cookies secure, set exact allowed origins, and put the API behind a trusted edge.

## Adapter contract

Adapters return raw records through `discover()` and map each record through
`normalize()`. The ingestor stores raw metadata and upserts by
`(source_id, external_id)`. A bad record is isolated and counted instead of
rolling back a successful page. Network adapters accept injected `httpx`
transports, so contract tests stay offline.

The MAST adapter is fixture-only until documented Roman preview/cutout fields
are confirmed. Setting `MAST_FIXTURE_ENABLED=true` permits explicit fixture
ingestion; it never probes private Mission Search endpoints.

### Scaling debt

The v0.2 API uses portable `ILIKE` search and an opaque base64 wrapper around an
offset cursor so SQLite and PostgreSQL tests behave identically. Add PostgreSQL
full-text/trigram indexes when catalog size justifies them. Before a large or
high-churn catalog, replace the cursor with a signed keyset containing the
selected sort value and stable item ID; offset pagination can shift when votes
or publication order change.
