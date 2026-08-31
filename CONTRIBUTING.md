# Contributing to RomanPics

Thanks for helping make Roman imagery easier to explore. Keep changes focused
and explain user-visible behavior and operational impact in the pull request.

## Development checks

The root check needs Node.js 22.13 or newer, Python 3.13, and
[`uv`](https://docs.astral.sh/uv/). It runs frontend lint/type checks, catalog
validation, OpenAPI lint and runtime drift checks, and a production build.

```bash
npm ci
npm run check
```

Run the service suites when their code or contracts may be affected:

```bash
(cd services/api && uv sync --locked --extra dev && uv run ruff check . && uv run pytest && uv build)
(cd services/worker && uv sync --locked --extra dev && uv run ruff check . && uv run pytest && uv build)
```

The worker supports Python 3.11 or newer; CI uses Python 3.12. Its PostgreSQL
tests use a disposable database through `ROMANPICS_TEST_DATABASE_URL`. Tests
must never point that variable at a shared or production database.

## Adding catalog content

The portable seed is [`data/catalog.json`](data/catalog.json). Its content-class
values are frontend manifest values:

- `flight-science`
- `simulation`
- `telescope` for ground-test/hardware content
- `mission-photo`
- `visualization`

The API normalizes these to uppercase enum values such as `FLIGHT_SCIENCE` and
`GROUND_TEST`; do not put API enums into the checked-in manifest.

Every item must include:

- stable `id`, `slug`, `sourceAdapter`, and `externalId` values;
- an authoritative `sourceUrl` and an upstream original or archive-product URL
  when one exists;
- `contentClass`, `contentLabel`, and a consistent `isFlightData` value;
- credit, rights text/URL, publication date, and descriptive alt text;
- reviewed remote image and thumbnail URLs on allowed HTTPS hosts;
- tags, technical `products`, and human-readable `provenance`; and
- enough plain-language context to avoid overstating what the image shows.

Include trustworthy preview dimensions when the provider supplies them; do not
invent dimensions merely to fill fields. Never copy an upstream original into
the repository. Prefer a provider-hosted web rendition. Never label a
simulation, artist concept, ground test, or image from another telescope as an
observation made by Roman.

Clusters must contain only one content class, their representative must be a
member, and every cluster, collection, or similarity reference must point to an
existing item. Run the offline validator after every catalog edit:

```bash
npm run catalog:check
```

The live check performs network requests to all checked-in source and thumbnail
URLs. Run it deliberately when reviewing upstream changes:

```bash
npm run catalog:links
```

## Adding a source adapter

Adapters live under `services/api/romanpics_api/adapters/`. An adapter must:

1. use a documented API or a reviewed, versioned manifest;
2. preserve the raw source record and normalize through the shared Python
   `SourceAdapter` contract;
3. make discovery and upserts idempotent;
4. expose source freshness and isolate per-record failures;
5. validate hosts, redirects, MIME types, and response-size limits;
6. preserve provenance, rights, versions, and supersession state; and
7. include deterministic fixtures and tests that do not require a live provider.

Never make the test suite depend on live NASA, STScI, or IPAC services. Inject a
fake HTTP transport. Never depend on an undocumented portal endpoint without an
isolated experiment, written risk assessment, and reviewed fallback.

MAST production ingestion stays gated until its public Roman interfaces are
documented and verified. Synthetic or recorded MAST fixtures must preserve
prompt-overwrite and final-supersession behavior.

## Changing the API or worker

The curated API contract is `docs/openapi.yaml`; `npm run api:contract` compares
its methods and operation IDs with the running FastAPI application. Update the
implementation, schema, tests, and contract together.

The queue contract is `services/api/docs/job-contract.json`. Queue payloads carry
catalog IDs, checksums, recipes, and fixed scopes—not arbitrary source URLs or
filesystem paths. Changes must remain compatible with the worker's validation,
PostgreSQL lease store, input hydration, and transactional result persistence.
Add an integration test for any change to render publication, embedding
persistence, retry, heartbeat, or stale-lease behavior.

Generated preview code must keep these safety properties:

- source URLs are resolved from trusted catalog relationships;
- network access and exact upstream hosts are explicitly enabled;
- every redirect and DNS result is revalidated;
- byte and MIME limits are enforced;
- only reviewed renderable L3 products may enter the fallback renderer; and
- temporary source bytes are removed after producing the small derivative.

## UX and accessibility

- Use plain language before archive terminology.
- Do not communicate content status by color alone.
- Keep controls keyboard accessible with visible focus.
- Use authoritative captions for alt text; do not invent object identities.
- Respect reduced motion and keep mobile image payloads small.
- Preserve a paginated path; infinite scroll cannot be the only navigation.
- Label fixture, simulated, site-generated, and flight-science states honestly.

Picture votes and similarity-group votes are intentionally distinct. Avoid any
ranking formula that rewards a group merely for containing more members.
Clustering changes must preserve or explicitly archive voted group identities.

## Pull-request checklist

- [ ] `npm run check` passes.
- [ ] Relevant API and worker suites pass.
- [ ] New catalog media has reviewed source, credit, rights, and classification.
- [ ] New network behavior is allowlisted, bounded, and covered by offline tests.
- [ ] User-visible behavior and deployment/configuration changes are documented.
- [ ] No upstream original, generated database, secret, or local environment file
      is committed.

Report security issues privately as described in [SECURITY.md](SECURITY.md), not
in a public issue.
