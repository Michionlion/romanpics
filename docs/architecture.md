# RomanPics architecture

Status: implemented launch-era reference stack with explicit operational gates.
The frontend, API, PostgreSQL schema, adapters, voting, and PostgreSQL worker
exist. Scheduled ingestion, routine worker operation, and the production MAST
adapter remain gated.

## Product definition

RomanPics is a consumer discovery layer over authoritative Roman sources. It
does not replace MAST, IRSA, or NASA media repositories.

The target meaning of “the entire catalog” is that every appropriate public
Roman-related record is discoverable and linked, not that every detector file
becomes a separate gallery card. Today the portable catalog has eight reviewed
launch-era records. During science operations, the gallery unit remains a stable
`gallery_item` that can group many archive products from one observation, sky
cell, target, filter stack, release, or outreach composite.

### Goals

- Make interesting Roman imagery findable without archive expertise.
- Link every record to an authoritative original and preserve provenance.
- Clearly distinguish flight science, simulations, visualizations, mission
  photography, and ground-test data.
- Group near-duplicates and related observations without hiding technical files.
- Let the community vote for both a similarity group and its best representative.
- Keep original science files upstream and operating cost modest.

### Non-goals

- Mirroring the MAST or IRSA archive.
- Serving general-purpose astronomy cutouts or arbitrary remote image proxies.
- Replacing scientific analysis tools.
- Making unreviewed AI claims about objects in an image.

## Implemented baseline and target topology

```text
                              ┌──────────────────────┐
NASA Images ────────────────> │                      │
NASA SVS ───────────────────> │ source adapters      │
IPAC/IRSA manifests ────────> │ + reconciliation     │
MAST Roman / subscriptions ─> │                      │
                              └──────────┬───────────┘
                                         │ normalized records/jobs
                              ┌──────────▼───────────┐
                              │ PostgreSQL 17        │
                              │ portable search      │
                              │ jobs + catalog       │
                              └──────┬────────┬──────┘
                                     │        │
                         ┌───────────▼─┐   ┌──▼────────────────┐
                         │ public API  │   │ background worker │
                         │ REST/JSON   │   │ previews/embed/   │
                         │ + OpenAPI   │   │ cluster/reconcile │
                         └──────┬──────┘   └──┬────────────────┘
                                │             │ small derivatives only
                         ┌──────▼──────┐   ┌──▼────────────────┐
                         │ web app     │   │ VPS disk or R2    │
                         │ explore +   │   │ optional preview  │
                         │ detail      │   │ cache             │
                         └─────────────┘   └───────────────────┘
```

The repository implements one FastAPI service, one PostgreSQL-backed jobs table,
and one optional worker profile. Render, embedding, stable-cluster graph, and
link-check results persist transactionally. Cluster replacement is serialized,
content-class partitioned, and reconciled to existing stable identities. No
Redis, Elasticsearch, Kafka, or microservice-per-source architecture is
justified.

| Surface | Current state |
| --- | --- |
| Frontend | Vinext application with API-aware SSR and explicit checked-in fallback |
| API | FastAPI `/v1`, curated OpenAPI 3.1 contract, ETags, reads, votes, and operator CLI |
| Database | PostgreSQL 17 in production-shaped Compose; SQLite only for local/test compatibility |
| Worker | Opt-in Compose `worker` profile with PostgreSQL leases, safe fetch, and durable preview/embedding/cluster/link-check persistence |
| Hosting | Separately hosted frontend plus VPS backend/Nginx bundle; no Netlify or VPS frontend package yet |
| MAST | Fixture-only until documented production Roman interfaces are verified |

## Frontend scope

### Routes

| Route | Purpose |
| --- | --- |
| `/` | Explore grid with search, friendly filters, newest/top/trending, and “Surprise me” |
| `/images/{slug}` | Large preview, plain-language caption, badges, credit, source/original links, technical details, related items |
| `/groups` | Similarity neighborhoods ranked by explicit group votes |
| `/groups/{slug}` | Group members and community-selected representative |
| `/collections` | Browse editorial paths through the launch-era catalog |
| `/collections/{slug}` | Editorial stories such as First Light or Galaxies |
| `/sky` | Prepared coordinate/footprint search with an honest pre-science empty state |
| `/journey` | Follow launch, commissioning, first-image, and science milestones |
| `/compare/filters` | Accessible same-region filter-comparison prototype |
| `/compare/field-of-view` | Explanatory Roman/Hubble/Webb field-of-view comparison |
| `/tools/color` | Teaching tool for assigned-color infrared composites |
| `/about/images` | Explain simulations, infrared color, data levels, sources, and rights |
| `/status` | Last successful sync and known source problems |
| `/embed/gallery` | Small, non-indexed, source-linked gallery card |
| `/feed.xml`, `/atom.xml` | Portable-catalog discovery feeds |

### Nontechnical defaults

- Search natural terms such as “spiral galaxies” or “the telescope being built.”
- Show `FLIGHT SCIENCE`, `SIMULATED`, `MISSION PHOTO`, `VISUALIZATION`, or
  `GROUND TEST` on every card; never rely on color alone.
- Put source, credit, observation/publication date, and “View original” near the
  image. Hide archive-specific fields under “Technical details.”
- Offer paginated grid and list views. Infinite scroll must not be the only path.
- Expand acronyms, explain pseudo-color, and use authoritative captions for alt text.
- Keep controls keyboard-complete, focus-visible, high contrast, and compatible
  with reduced motion.

## Source adapters

All providers implement a narrow Python boundary so an evolving upstream schema
does not leak into the public API. Asset and preview candidates travel inside the
normalized record rather than through separate public methods:

```python
class SourceAdapter:
    async def discover(
        self, cursor: str | None, modified_since: datetime | None
    ) -> SourcePage: ...

    async def normalize(self, record: dict[str, object]) -> NormalizedRecord: ...
```

Implemented adapters:

| Adapter | Initial behavior |
| --- | --- |
| `nasa_images` | REST search and asset-manifest endpoints; use official renditions |
| `nasa_svs` | Roman search/detail JSON; preserve alt text, credits, and media sizes |
| `ipac_manifest` | Versioned, reviewed manifest for simulations without a stable catalog API |
| `mast_roman` | Fixture-only lifecycle contract; production Mission Search/DAAPI/astroquery access remains disabled |
| `static_catalog` | Checked-in records and graph for launch-era and future special releases |

Rules for every adapter:

- Preserve the raw upstream response for debugging.
- Upsert by `(source_id, external_id)` and make retries idempotent.
- Track cursor/watermark, last success, last error, and record counts.
- Overlap incremental watermarks by 48 hours, then reconcile the full source weekly.
- Validate that canonical, original, and preview URLs resolve on an allowlisted host.
- Never scrape an undocumented portal when a documented API or reviewed manifest exists.

## Canonical data model

### `source`

`id`, `adapter`, `display_name`, `canonical_host`, `terms_url`, `cursor`,
`poll_interval`, `last_success_at`, `last_error_at`, `last_error`.

### `source_record`

`id`, `source_id`, `external_id`, `canonical_url`, `upstream_created_at`,
`upstream_updated_at`, `etag`, `checksum`, `raw_metadata`, `state`,
`superseded_by_id`, timestamps.

### `observation`

`id`, `mission`, `observation_id`, `program_id`, `survey`, `instrument`, `mode`,
`optical_elements[]`, `target_name`, `ra`, `dec`, `healpix`, `footprint`,
`observed_start`, `observed_end`, `data_level`, `product_version`,
`pipeline_version`, `release_name`.

### `archive_product`

`id`, `observation_id`, `source_record_id`, `external_url`, `media_type`,
`byte_size`, `subtype`, `is_original`, `derived_from_id`, `active`, timestamps.

### `gallery_item`

`id` (stable UUID), `slug`, `title`, `plain_summary`, `content_class`,
`is_flight_data`, `primary_source_record_id`, `primary_observation_id`,
`published_at`, `editorial_state`, `search_document`, timestamps.

### `item_asset` and `rendition`

Join a gallery item to one or more archive products. A rendition records
`provider`, `url`, `width`, `height`, `format`, `is_site_derivative`, `recipe`,
`alt_text`, `credit`, `rights`, `rights_url`, and `last_verified_at`.

### Discovery and community tables

- `tag` / `item_tag` — controlled concepts plus plain-language aliases.
- `embedding` — item ID, model/version, vector, perceptual hash.
- `cluster` / `cluster_member` — algorithm version, stable label, centroid,
  similarity, rank, active/archived state.
- `active_vote` — one current vote per actor, target kind, and target ID.
- `vote_event` — append-only actor, target, operation, network HMAC, and timestamp.
- `vote_total` — materialized count per target.
- `collection` / `collection_item` — editorial sequences.
- `ingest_run` / `job` — source health, retry, and observability.

Current search uses portable case-insensitive substring matching so the same API
works in PostgreSQL and SQLite tests. The schema already stores a HEALPix key for
future coordinate prefiltering. Add PostgreSQL full-text search and `pg_trgm`
only after relevance or latency measurements justify them; add pgvector HNSW
only when brute-force similarity becomes a measured problem. Neither extension
is a deployed dependency today.

## Ingestion flow

1. An operator CLI invocation starts a run today; a scheduled poll, MAST
   subscription, or release trigger can invoke the same service later.
2. The adapter discovers changed records and stores the raw response.
3. Normalization validates content class, provenance, rights, and upstream IDs.
4. Asset resolution selects an official remote rendition where possible.
5. Records and assets are upserted atomically; superseded versions remain linked.
6. The worker calculates hashes, embeddings, and group candidates when its
   Compose profile is active.
7. Render and embedding results persist transactionally. Cluster membership and
   directional similarity edges replace the prior computed graph atomically,
   while stable-ID reconciliation preserves voted group identity.
8. Search documents and cached counts are refreshed by ingestion/seed logic.
9. A source-health row records duration, counts, errors, and the next cursor.

Failures are retryable per record. One malformed record must not roll back an
entire source run.

## Preview policy

Priority:

1. source-provided browser rendition;
2. documented MAST preview/cutout;
3. official outreach composite associated with the archive record;
4. small site-generated preview from an L3 cutout/mosaic.

Generated previews use deterministic 320px and 768px WebP files. For
single-filter science images, use a documented sigma-clipped/asinh stretch. For
multi-filter color, store the filter-to-channel recipe and explain that colors
are assigned. Delete temporary source bytes immediately.

No request handler may accept an arbitrary URL to proxy or transform. The worker
must validate DNS, schemes, redirect targets, MIME type, and byte limits against
an explicit source allowlist.

## Similarity and groups

Similarity has three understandable layers:

1. **Deterministic families** — same observation, target/sky cell, visit, or
   filter stack.
2. **Duplicate detection** — upstream checksum and perceptual hash.
3. **Visual + semantic neighbors** — a small OpenCLIP/SigLIP image embedding
   fused with trusted metadata similarity.

The worker partitions by content class before graph clustering so cleanroom
photography cannot mix with flight-science images. The portable seed exposes
reviewed nearest neighbors immediately. The worker can publish a computed graph
atomically; a nightly/weekly production schedule is not enabled yet.

Cluster IDs must remain stable. Match a new clustering run to previous clusters
using membership overlap and centroid distance. If a voted cluster splits or
merges substantially, archive the old snapshot and create new IDs rather than
silently moving its votes.

Automatic group labels come from trusted metadata and reviewed tags. AI may
suggest labels or missing alt text, but it cannot publish scientific assertions
without review.

## Votes and ranking

Picture votes and group votes are separate:

- **Top pictures:** trusted picture-vote count.
- **Top groups:** explicit group-vote count; group size contributes nothing.
- **Representative:** an explicitly stored/seeded member today; member-vote-based
  automatic selection is a future policy.
- **Trending:** currently uses the same aggregate vote ordering as top; a
  time-decayed recent-vote score is future work.
- **New:** observation/publication date, not ingestion time.

MVP anonymous voting:

- issue a random signed `HttpOnly`, `Secure`, `SameSite=Lax` visitor cookie;
- enforce one active vote per `(actor, target_kind, target_id)` and allow undo;
- keep short-lived daily HMACs of IP prefixes for abuse throttling, never raw IPs;
- verify `Origin`, apply CSRF protection, and trust client IPs only from the edge;
- add a challenge such as Turnstile only if observed abuse justifies it; and
- retain append-only vote events for audit and expose aggregate totals only.

The signed cookie, active-vote uniqueness, exact-Origin validation, daily
network-prefix HMAC, append-only events, aggregate totals, and replaceable
in-process limiter are implemented. Nginx supplies a second mutation limit. The
challenge is not implemented.

Optional email/passkey accounts can later sync favorites but are not required to
browse or vote.

## Public API

The public surface is cache-friendly REST with cursor pagination, one-based page
compatibility, ETags, appropriate `Cache-Control`, RFC 7807 problem responses,
and an OpenAPI 3.1 document. The curated
[OpenAPI contract](openapi.yaml) is linted and checked against FastAPI's runtime
methods and operation IDs in CI.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/v1/items` | search/filter/sort gallery items |
| GET | `/v1/items/{id-or-slug}` | one item with provenance and rendition |
| GET | `/v1/items/{id}/similar` | nearest related items |
| GET | `/v1/items/{id}/products` | upstream technical products |
| GET | `/v1/clusters` | browse similarity groups |
| GET | `/v1/clusters/{id-or-slug}` | members and representative |
| GET | `/v1/collections` | published editorial collections |
| GET | `/v1/collections/{slug}` | editorial collection |
| GET | `/v1/search/suggest?q=` | suggestions |
| GET | `/v1/facets` | filter counts |
| GET | `/v1/sources/status` | freshness and known errors |
| GET | `/v1/surprise` | one no-store discovery result by mood/subject |
| PUT/DELETE | `/v1/me/votes/items/{id}` | add/remove picture vote |
| PUT/DELETE | `/v1/me/votes/clusters/{id}` | add/remove group vote |

Every item response includes `content_class`, explicit flight/simulation state,
source and archive URLs, remote original, preview, credit, rights, and any site
transformation recipe.

## Deployment

The repository includes a Vinext frontend, FastAPI/SQLAlchemy service, Alembic
migration, PostgreSQL 17 Compose service, and opt-in Python worker. NASA Images,
SVS, and reviewed manifests can be synchronized now; only production MAST remains
gated pending a documented preview path.

| Option | Good fit | Limitations | Decision |
| --- | --- | --- | --- |
| Existing VPS | API, worker, PostgreSQL, controlled preview disk, predictable cost | owner operates backups, updates, monitoring; frontend image is not packaged | preferred stateful backend home |
| Sites | Existing Vinext-compatible frontend project and preview deployments | separately hosted from the VPS API; cross-site cookie/CORS configuration may be required | implemented frontend path |
| Netlify free | possible future frontend/deploy-preview host | no checked-in `netlify.toml` or static-export contract; no astronomy processing or PostgreSQL | not currently supported |
| Object storage/CDN | small generated previews | another service to operate; respect rights | add only when VPS disk/egress is measured |

The nearby VPS edge is **Nginx + Certbot**, not Traefik. The repository includes
a dedicated external Docker-network attachment, API virtual-host templates, and
a read-only preview-volume mount. It must not publish the neighboring website
directory or copy its secrets into this repository.

Deployed backend service shape:

```text
separately hosted Vinext frontend
└── HTTPS API origin on edge Nginx
    ├── FastAPI on isolated edge network
    ├── private PostgreSQL 17 catalog network
    └── optional worker on catalog + egress networks
```

`compose.yaml` is backend-only. Serving the frontend from the VPS requires a
separately reviewed web image/service and virtual host. See
[`infra/README.md`](../infra/README.md) for exact deployment boundaries.

## Security, privacy, and operations

- Allowlist all upstream hosts and validate redirects; block private/link-local IPs.
- Set strict CSP, `Referrer-Policy`, frame restrictions, and MIME sniffing protection.
- Sanitize upstream HTML and render descriptions as text by default.
- Never log cookies, tokens, raw IPs, or arbitrary upstream payloads.
- Back up PostgreSQL and test restore; derived previews are rebuildable.
- Expose source freshness and degraded adapters without taking the whole site down.
- Keep API p95 under 300 ms from cache/database for normal list/detail reads.
- Keep the first gallery load under roughly 1 MB and lazy-load below-fold media.
- Verify at least 95% of outbound links weekly and surface dead links internally.

## Open questions before production MAST ingestion

1. Which documented Roman API fields remain stable after first-flight products?
2. When will supported preview and WFI cutout URLs be available outside Mission Search?
3. What are the permitted hotlink/cache headers for each provider rendition?
4. Which prompt L3 products are most suitable as one consumer-facing image unit?
5. How should a prompt gallery item migrate to a preserved data-release product?
6. What thumbnail volume and egress actually occur after first light?
