# RomanPics

RomanPics is an unofficial, open-source explorer for discovering imagery
connected to NASA's Nancy Grace Roman Space Telescope and following every item
back to its authoritative source.

> RomanPics is independent and is not affiliated with or endorsed by NASA,
> STScI, or IPAC. Upstream images and data retain their original credits and
> terms.

Roman launched on August 30, 2026. There are no flight-science images yet; NASA
expects the first images in early 2027 after the observatory reaches L2 and
completes commissioning. Until then, RomanPics presents official mission media,
visualizations, ground-test material, and science simulations with explicit
labels that never imply they were observed by Roman.

## What is implemented

The checked-in launch-era catalog currently contains eight reviewed NASA Images
and NASA SVS records, three content-class-pure similarity groups, and five
editorial collections. The application includes:

- searchable, paginated exploration with plain-language filters and sorting;
- item, similarity-group, and collection pages with credits and upstream links;
- “Surprise me,” RSS, Atom, a small embed, mission-journey, comparison, color,
  and future sky-search experiences;
- an explicit fixture mode for inexpensive frontend previews;
- a FastAPI `/v1` API backed by SQLAlchemy, Alembic, and PostgreSQL;
- idempotent NASA Images, NASA SVS, and reviewed-manifest ingestion;
- signed anonymous item and group votes with undo, origin checks, audit events,
  aggregate totals, and edge/application rate limits;
- deterministic IDs, source health, ETags, collections, similarities, and
  technical-product metadata; and
- an opt-in PostgreSQL worker that leases jobs, renders bounded 320 px and
  768 px WebP previews, persists renditions and embeddings, checks links, and
  computes content-class-separated similarity candidates.

When no API base is configured, reads come from `data/catalog.json` and votes
are stored only in that browser's `localStorage`. With the API configured,
votes are persisted in PostgreSQL. The frontend deliberately falls back to the
checked-in catalog if a read fails and labels the gallery transport accordingly.

Not yet production-operated: scheduled live ingestion, routine similarity and
link-check schedules, an admin editing interface, and the production MAST Roman
adapter. The worker now publishes computed clusters and directional similarity
edges atomically while preserving stable cluster identities. MAST remains
fixture-gated until documented public Roman preview and cutout interfaces are
confirmed.

## Source strategy

| Availability | Authoritative source | RomanPics behavior |
| --- | --- | --- |
| In the current catalog | NASA Image and Video Library | Mission, hardware, launch, and outreach records with provider-hosted renditions |
| In the current catalog | NASA Scientific Visualization Studio | Simulations, visualizations, mission media, credits, alt text, and web-sized stills |
| Adapter/manifest ready | IPAC/IRSA | Only reviewed, versioned simulation manifests; no undocumented scraping |
| Fixture contract ready | MAST | Synthetic/recorded lifecycle tests and render gating; no live production ingestion yet |
| Science operations | MAST Roman archive | Public WFI/Coronagraph observations, products, provenance, and supported previews |

See [Roman data sources](docs/roman-data-sources.md) and
[MAST readiness](docs/mast-readiness.md) for current evidence and limitations.

## System shape

RomanPics is a metadata-and-preview index, not a data mirror:

```text
NASA Images / NASA SVS / reviewed manifests / future MAST
                         │
                         ▼
              adapters + reconciliation
                         │
                         ▼
                   PostgreSQL 17
                    │         │
                    ▼         ▼
              FastAPI /v1   worker profile
                    │       render/embed/check
                    ▼         │
              Vinext web      └─> small WebP previews only
```

Original science products remain upstream. RomanPics prefers an official web
rendition and generates a small derivative only when a reviewed, renderable L3
product has no supported preview. The worker deletes temporary source bytes.
Current search is portable database substring search; PostgreSQL full-text
search, `pg_trgm`, and pgvector are future optimizations, not deployed
dependencies.

- [Architecture and API](docs/architecture.md)
- [OpenAPI contract](docs/openapi.yaml)
- [Worker pipeline](services/worker/docs/pipeline.md)
- [Phased roadmap](docs/roadmap.md)
- [Product ideas](docs/product-ideas.md)

## Run the frontend in fixture mode

Requirements: Node.js 22.13 or newer.

```bash
npm ci
npm run dev
```

Open `http://localhost:3000`. Leave `NEXT_PUBLIC_API_BASE` and
`ROMANPICS_INTERNAL_API_BASE` unset to use the checked-in catalog.

## Run the API locally

Requirements: Python 3.13 and [`uv`](https://docs.astral.sh/uv/). From a second
terminal:

```bash
cd services/api
uv sync --locked --extra dev
export DATABASE_URL=sqlite:///./romanpics.db
export ENVIRONMENT=development
export COOKIE_SECURE=false
uv run alembic upgrade head
uv run romanpics seed --manifest ../../data/catalog.json
uv run uvicorn romanpics_api.main:app --reload
```

Start the frontend with these non-secret local values:

```bash
NEXT_PUBLIC_SITE_URL=http://localhost:3000 \
NEXT_PUBLIC_API_BASE=http://localhost:8000 \
ROMANPICS_INTERNAL_API_BASE=http://localhost:8000 \
npm run dev
```

Canonical API routes start at `/v1`; API documentation is available from the
running service at `/docs` and `/openapi.json`. See
[the API README](services/api/README.md) for adapter and CLI examples.

## Validate a change

The full root check also validates the catalog, lints the curated OpenAPI file,
compares it with FastAPI's runtime routes, type-checks, and builds the frontend.
It therefore needs Node.js, Python 3.13, and `uv`.

```bash
npm ci
npm run check

(cd services/api && uv sync --locked --extra dev && uv run ruff check . && uv run pytest && uv build)
(cd services/worker && uv sync --locked --extra dev && uv run ruff check . && uv run pytest && uv build)
```

The worker supports Python 3.11 or newer; CI uses Python 3.12 and also exercises
its PostgreSQL lease and persistence integration tests.

## Deploy

The repository supports two deliberately separate deployment surfaces:

- The Vinext frontend is configured for Sites and can also run in fixture-only
  mode. It is not currently packaged as a Netlify site or VPS web container.
- `compose.yaml` deploys PostgreSQL, migrations, the idempotent seed, FastAPI,
  and an optional `worker` profile. Nginx/Certbot integration for the existing
  VPS lives in [`infra/README.md`](infra/README.md).

Netlify remains a possible future frontend adapter, but no `netlify.toml` or
static-export contract is checked in. Similarly, serving the frontend from the
VPS requires adding and testing a web image/service; the current Compose bundle
is backend-only.

## Contributing

Issues and pull requests are welcome. Preserve three invariants:

1. Every item links to an authoritative source and carries its credit and rights
   information.
2. Simulated, ground-test, visualization, mission-photo, and flight-science
   content are never conflated.
3. RomanPics does not routinely retain or proxy original science products.

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing the catalog, an adapter,
or the worker contract. Report vulnerabilities according to
[SECURITY.md](SECURITY.md).

## License and media

Application code and project-authored documentation are licensed under the
[MIT License](LICENSE). That license does **not** cover third-party imagery or
data linked from the catalog. See [NOTICE](NOTICE) and each source record for
credits and use terms.

## Primary references

- [NASA Roman mission status](https://science.nasa.gov/mission/roman-space-telescope/)
- [Roman in MAST](https://archive.stsci.edu/missions-and-data/roman)
- [Roman archive documentation](https://roman-docs.stsci.edu/data-handbook/accessing-wfi-data/the-roman-archive-in-mast)
- [NASA Images API](https://images.nasa.gov/docs/images.nasa.gov_api_docs.pdf)
- [NASA SVS API](https://svs.gsfc.nasa.gov/help/)
