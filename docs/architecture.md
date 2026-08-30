# RomanPics architecture

Status: proposed architecture for the MVP and science-operations transition.

## Product definition

RomanPics is a consumer discovery layer over authoritative Roman sources. It
does not replace MAST, IRSA, or NASA media repositories.

“The entire catalog” means every public Roman-related record is discoverable and
linked, but not every detector file becomes a separate gallery card. The gallery
unit is a stable `gallery_item` that can group many archive products from one
observation, sky cell, target, filter stack, release, or outreach composite.

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

## Proposed topology

```text
                              ┌──────────────────────┐
NASA Images ────────────────> │                      │
NASA SVS ───────────────────> │ source adapters      │
IPAC/IRSA manifests ────────> │ + reconciliation     │
MAST Roman / subscriptions ─> │                      │
                              └──────────┬───────────┘
                                         │ normalized records/jobs
                              ┌──────────▼───────────┐
                              │ PostgreSQL           │
                              │ FTS + pg_trgm        │
                              │ pgvector when needed │
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

One worker and a PostgreSQL-backed jobs table are enough initially. Do not add
Redis, Elasticsearch, Kafka, or a microservice per source until evidence demands
them.

## Frontend scope

### Routes

| Route | Purpose |
| --- | --- |
| `/` | Explore grid with search, friendly filters, newest/top/trending, and “Surprise me” |
| `/images/{slug}` | Large preview, plain-language caption, badges, credit, source/original links, technical details, related items |
| `/groups` | Similarity neighborhoods ranked by explicit group votes |
| `/groups/{slug}` | Group members and community-selected representative |
| `/collections/{slug}` | Editorial stories such as First Light or Galaxies |
| `/sky` | Later: coordinate/footprint map and cone search |
| `/about/images` | Explain simulations, infrared color, data levels, sources, and rights |
| `/status` | Last successful sync and known source problems |

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

All providers implement a narrow boundary so an evolving upstream schema does
not leak into the public API:

```ts
interface SourceAdapter {
  discover(cursor?: string, modifiedSince?: string): Promise<SourcePage>;
  normalize(record: unknown): Promise<NormalizedRecord>;
  listAssets(record: unknown): Promise<ExternalAsset[]>;
  resolvePreview(record: unknown): Promise<PreviewCandidate | null>;
}
```

Planned adapters:

| Adapter | Initial behavior |
| --- | --- |
| `nasa_images` | REST search, asset manifest, and metadata endpoints; use official renditions |
| `nasa_svs` | Roman search/detail JSON; preserve alt text, credits, and media sizes |
| `ipac_manifest` | Versioned, reviewed manifest for simulations without a stable catalog API |
| `mast_roman` | Mission Search/DAAPI/astroquery only through documented interfaces; prefer L3 gallery records |
| `editorial` | Checked-in records for important first-light releases and cross-source composites |

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
`alt_text`, `credit`, `rights_url`, and `last_verified_at`.

### Discovery and community tables

- `tag` / `item_tag` — controlled concepts plus plain-language aliases.
- `embedding` — item ID, model/version, vector, perceptual hash.
- `cluster` / `cluster_member` — algorithm version, stable label, centroid,
  similarity, rank, active/archived state.
- `vote_event` — actor, target kind, target ID, operation, timestamp.
- `vote_total` — materialized count per target.
- `collection` / `collection_item` — editorial sequences.
- `ingest_run` / `job` — source health, retry, and observability.

Use PostgreSQL full-text search plus `pg_trgm` first. Store a HEALPix key for
coordinate prefiltering. Add pgvector HNSW only when the catalog is large enough
for brute-force similarity to become a measured problem.

## Ingestion flow

1. A scheduled poll, MAST subscription, or manual release trigger starts a run.
2. The adapter discovers changed records and stores the raw response.
3. Normalization validates content class, provenance, rights, and upstream IDs.
4. Asset resolution selects an official remote rendition where possible.
5. Records and assets are upserted atomically; superseded versions remain linked.
6. The worker calculates hashes, embeddings, tags, and group candidates.
7. Search documents and cached counts are refreshed.
8. A source-health row records duration, counts, errors, and the next cursor.

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

Partition by content class before visual clustering so cleanroom photography
does not mix with flight-science images. Expose nearest neighbors immediately;
run HDBSCAN or graph clustering on a nightly/weekly schedule.

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
- **Representative:** highest-ranked picture inside a group.
- **Trending:** recent votes with time decay.
- **New:** observation/publication date, not ingestion time.

MVP anonymous voting:

- issue a random signed `HttpOnly`, `Secure`, `SameSite=Lax` visitor cookie;
- enforce one active vote per `(actor, target_kind, target_id)` and allow undo;
- keep short-lived daily HMACs of IP prefixes for abuse throttling, never raw IPs;
- verify `Origin`, apply CSRF protection, and trust client IPs only from the edge;
- invoke a challenge such as Turnstile only after suspicious behavior;
- retain append-only vote events for audit and expose aggregate totals only.

Optional email/passkey accounts can later sync favorites but are not required to
browse or vote.

## Public API

The public surface is cache-friendly REST with cursor pagination, ETags,
appropriate `Cache-Control`, RFC 7807 problem responses, and an OpenAPI 3.1
document. See [openapi.yaml](openapi.yaml) for the draft contract.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/v1/items` | search/filter/sort gallery items |
| GET | `/v1/items/{id-or-slug}` | one item with provenance and rendition |
| GET | `/v1/items/{id}/similar` | nearest related items |
| GET | `/v1/items/{id}/products` | upstream technical products |
| GET | `/v1/clusters` | browse similarity groups |
| GET | `/v1/clusters/{id-or-slug}` | members and representative |
| GET | `/v1/collections/{slug}` | editorial collection |
| GET | `/v1/search/suggest?q=` | suggestions |
| GET | `/v1/facets` | filter counts |
| GET | `/v1/sources/status` | freshness and known errors |
| PUT/DELETE | `/v1/me/votes/items/{id}` | add/remove picture vote |
| PUT/DELETE | `/v1/me/votes/clusters/{id}` | add/remove group vote |

Every item response includes `content_class`, explicit flight/simulation state,
source and archive URLs, remote original, preview, credit, rights, and any site
transformation recipe.

## Deployment decision

The repository's current UI is a lightweight Vinext prototype. The production
backend should be deployed only after the first source spike validates real MAST
records and preview behavior.

| Option | Good fit | Limitations | Decision |
| --- | --- | --- | --- |
| Existing VPS | API, worker, PostgreSQL/pgvector, controlled disk/cache, predictable cost | owner operates backups, updates, monitoring | preferred MVP production home |
| Netlify free | frontend and pull-request previews | usage/credit limits; no place for astronomy processing or PostgreSQL | optional frontend only |
| Object storage/CDN | small generated previews | another service to operate; respect rights | add only when VPS disk/egress is measured |

The nearby VPS edge was inspected and is **Nginx + Certbot**, not Traefik. A
future deployment should join a dedicated Docker network and add a narrowly
scoped Nginx virtual host; it must not publish the neighboring website directory
or copy its secrets into this repository.

Suggested VPS services:

```text
edge Nginx
└── romanpics-web/API
    └── private application network
        ├── PostgreSQL 16 + pgvector
        └── one scheduled worker
```

The exact frontend runtime can stay flexible until the backend slice begins.
Avoid splitting frontend hosting from the API unless Netlify previews materially
improve the contribution workflow.

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

## Open questions to validate in the source spike

1. Which documented Roman API fields remain stable after first-flight products?
2. When will supported preview and WFI cutout URLs be available outside Mission Search?
3. What are the permitted hotlink/cache headers for each provider rendition?
4. Which prompt L3 products are most suitable as one consumer-facing image unit?
5. How should a prompt gallery item migrate to a preserved data-release product?
6. What thumbnail volume and egress actually occur after first light?

