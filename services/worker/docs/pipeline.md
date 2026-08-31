# Worker and similarity pipeline

## Job boundaries

The initial queue recognizes four job types:

- `render`: resolve an item/product relationship, fetch the allowlisted FITS/ASDF
  product temporarily, and write content-addressed previews;
- `embed`: verify the source-record checksum, resolve an existing browser rendition,
  and combine its visual descriptor with catalog metadata;
- `cluster`: verify the ingest-run/source relationship, load current embeddings,
  hard-partition by content class, and group records;
- `link-check`: accept only the fixed `catalog` scope and probe URLs selected from
  catalog tables with HEAD or a non-consumed one-byte range GET.

All payloads are validated against [`job-contract.json`](job-contract.json). There are
exactly four job types. Job payloads do not accept a URL or local path; a database
resolver obtains required inputs by ID and verifies product attachment, record state,
checksum, and ingest-run ownership. The independent source policy then enforces exact
hosts, public DNS answers, redirects, MIME types, and byte limits.

Render result persistence locks and rechecks the item/product/source relationship,
upserts each HTTPS WebP rendition, and publishes only when both conditions still hold:
the item is `draft` and `metadata_json.publication_gate` is exactly `"render"`. In
that transaction it removes the gate, clears only the known
`Awaiting a bounded site-generated preview.` note, and inserts the deduplicated embed
job. Hidden or manually ungated items cannot be accidentally published. Retries reuse
stable rendition IDs and unique URLs. Embed persistence similarly locks and rechecks
the item/source/checksum tuple before upserting `(item_id, model, version)`.

Generated previews cross a `PreviewStore` boundary. The included local implementation
writes atomically and returns a storage URI plus an optional configured public URL;
the catalog therefore never derives a web URL from a filesystem path. A production
S3-compatible/R2 adapter can implement the same single `put_file` method. Suggested
configuration is `ROMANPICS_PREVIEW_BUCKET`, `ROMANPICS_PREVIEW_ENDPOINT`,
`ROMANPICS_PREVIEW_PUBLIC_BASE_URL`, and provider credentials injected as runtime
secrets. Object keys are already content addressed, so uploads may be immutable with
long cache lifetimes. Do not make the bucket public unless a CDN/custom domain and
the intended CORS policy are configured.

SQLite provides a completely local implementation for tests and one-process
development. The psycopg 3 `PostgresJobStore` uses the backend's canonical table and
an atomic claim CTE shown in [`postgres_jobs.sql`](postgres_jobs.sql).
`FOR UPDATE SKIP LOCKED` permits multiple workers without Redis. Attempts increment at
claim time, failures use bounded exponential backoff, a background heartbeat extends
the lease, and lease recovery requeues abandoned work or marks it `failed` after its
final attempt. `cancelled` rows are never claimable.

## Similarity and identity are separate

`group_similar_items` produces a fresh partition:

1. hard-partition by `content_class` (science, simulation, mission photo, hardware,
   visualization, and so on);
2. add deterministic edges for shared upstream observation/product-family keys;
3. add above-threshold edges from each item's cosine k-nearest neighbors;
4. return connected components, including singletons.

The visual descriptor is intentionally lightweight. It allows the surrounding
pipeline to mature without committing the public taxonomy to a model. OpenCLIP and
SigLIP conform to the same interface, are lazy optional dependencies, and never
download weights unless a caller explicitly opts in.

`StableClusterReconciler` then maps new components to prior IDs by deterministic
maximum overlap. The strongest child inherits an ID after a split; the strongest
parent contributes its ID after a merge. Changed memberships create a new immutable
version. The result includes:

- `superseded` archives for older versions of a continuing stable ID;
- `merged_into` archives for identities absorbed by a survivor;
- `split_into` archives when an old identity has no inheriting child;
- `disappeared` archives when none of its members remain;
- explicit split/merge lineage edges for audit and vote migration policy.

Votes should attach to `(cluster_id, version)` while a separate policy decides whether
and how to display historical votes on a new version. This prevents a major regroup
from silently transferring endorsement to unrelated imagery.

## MAST prompt-product contract

The fixtures are deliberately MAST-shaped but synthetic. They establish rules before
live Roman records exist:

- a URI plus content token is a generation, not a permanent immutable object;
- a checksum/content change at the same prompt URI archives the old generation as
  `replaced` and emits `overwritten`;
- a final product replacing a prompt generation archives it as `superseded`;
- replaying the same response is idempotent;
- metadata-only changes do not fabricate an image generation.

When MAST publishes final Roman field names, update the row normalizer and add new
recorded/synthetic contract fixtures while preserving these lifecycle invariants.
