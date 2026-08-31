# RomanPics roadmap

The roadmap is staged around real product gates rather than fixed science dates.
Mission and archive schedules can change.

Status language used below:

- **Done** — implemented and exercised in CI or the checked-in application.
- **Built, not yet operated** — code exists, but scheduling, production data, or
  an operator decision is still required.
- **Pending** — not implemented.

## Phase 0 — launch-era foundation

- **Done:** independent project identity, source policy, media notice, and public
  contribution/security guidance.
- **Done:** eight-item reviewed `data/catalog.json` seed with provenance, content
  classes, upstream products, three same-class groups, five collections, and
  explicit similarities.
- **Done:** offline schema/host/credit/class/graph validation in normal CI.
- **Done:** scheduled GitHub check for the checked-in source and thumbnail URLs.
- **Done:** research covering NASA Images, NASA SVS, IPAC/IRSA, MAST, prompt
  products, overwrite behavior, and future preview/cutout constraints.
- **Pending:** confirm supported production Roman preview/cutout surfaces with
  the MAST Help Desk before enabling live MAST ingestion.

Exit gate: met for the checked-in catalog. Every current item has an authoritative
source, content class, credit, and remote rendition, and the UI does not describe
simulations as Roman observations.

## Phase 1 — launch-to-first-light MVP

- **Done:** searchable and paginated gallery, detail pages, top/new/trending
  controls, facets, shareable query parameters, surprise modes, and graceful
  fixture fallback.
- **Done:** PostgreSQL 17 schema, Alembic baseline, deterministic seed,
  idempotent ingestion runs, source status, reconciliation safeguards, and
  FastAPI `/v1` reads.
- **Done:** NASA Images, NASA SVS, reviewed generic/IPAC manifests, and
  fixture-only MAST adapters.
- **Done:** five editorial collections and read APIs.
- **Done:** signed anonymous item/group votes, undo, append-only audit events,
  materialized totals, exact-origin checks, network-prefix HMACs, and edge plus
  application rate limits.
- **Done:** CLI editorial-state transition, vote audit, total rebuild, source
  status, synchronization, and database link-check commands.
- **Built, not yet operated:** regular live NASA/IPAC sync and production-database
  link-check schedules. GitHub's weekly workflow checks only the portable seed.
- **Pending:** reviewed editing UI or richer CLI for title, summary, class,
  rights, and alt-text changes.
- **Pending:** automated browser accessibility tests and a mobile payload budget.

Exit gate: partially met. The code can rebuild the launch seed without retaining
upstream originals, but production scheduling and operational monitoring must be
enabled and observed before calling the MVP unattended.

## Phase 2 — similarity and community

- **Done:** exact SHA-256 and perceptual hashes, deterministic lightweight
  embeddings, and optional OpenCLIP/SigLIP adapters.
- **Done:** content-class-separated cosine neighbors, deterministic family edges,
  stable-cluster reconciliation, and split/merge/disappearance lineage tests.
- **Done:** “More like this,” group index/detail pages, explicit group votes, and
  separately voted member pictures.
- **Done:** RSS, Atom, an embeddable gallery card, source-health UI, and vote-audit
  tooling.
- **Built, not yet operated:** PostgreSQL worker leases, heartbeat/recovery,
  input hydration, rendering and embedding persistence, stable cluster
  reconciliation, atomic cluster/member/directional-edge replacement, and
  durable link-check history. The worker is opt-in through Compose's `worker`
  profile.
- **Pending:** routine similarity schedules, moderation controls, and reviewed
  automatic group labels.
- **Pending:** optional email/passkey accounts for synced favorites.

Exit gate: not yet met in production. The algorithms, safety contracts, and
stable publication path are tested; scheduled computation must be operated and
monitored without mixing content classes or silently transferring voted
identities.

## Phase 3 — first light and science operations

- **Done:** synthetic/recorded prompt overwrite, idempotency, and final
  supersession fixtures.
- **Done:** ingestion gate for items without a browser rendition: only renderable
  L3 FITS/ASDF products may queue a bounded preview; L1/L2 products stay out.
- **Done:** deterministic 320 px and 768 px WebP renderer, documented stretch/RGB
  recipes, content-addressed storage, temporary cleanup, and transactional
  publication of render-gated draft items.
- **Pending:** validate a production `mast_roman` adapter against public WFI and
  Coronagraph records and supported preview/cutout fields.
- **Pending:** group L1/L2 detector products beneath stable observation-family
  pages while preferring L3 mosaics for gallery cards.
- **Pending:** choose and operate polling/subscription cadence for prompt products
  and periodic full reconciliation.
- **Pending:** migrate prompt items to preserved data-release products without
  losing URLs, votes, groups, or provenance.

Exit gate: new public observations become discoverable within one operated
ingestion cycle, and an upstream overwrite/removal cannot silently break a voted
RomanPics item.

## Phase 4 — richer discovery

- **Done as preparatory experiences:** honest empty-state cone search, field-of-view
  explainer, accessible filter-comparison prototype, infrared color-composer
  teaching tool, journey page, RSS/Atom, and gallery embed.
- **Pending:** data-connected footprint map and indexed HEALPix/cone results in
  the frontend.
- **Pending:** aligned same-sky multi-filter comparisons, time-domain blink views,
  and light-curve companions backed by real products.
- **Pending:** cross-mission coordinate links to Hubble, Webb, Euclid, and Rubin.
- **Pending:** saved/shareable user collections and reviewed community tags.
- **Pending:** documented API client examples and richer embed controls.

## Success measures and verification state

| Measure | Current verification |
| --- | --- |
| Every current card exposes source, credit/rights, and content class | Enforced for the portable seed by `npm run catalog:check` |
| No original science product retained after processing | Enforced by worker design/tests; verify on the production preview volume |
| At least 95% of public links valid | Scheduled portable-seed check exists; production-database reporting still needs a schedule and alert |
| Source freshness and degraded adapters visible | API implemented; production status-page mode and monitoring still need verification |
| First gallery load roughly 1 MB or less | Target only; no CI payload budget yet |
| Keyboard navigation and reduced motion | Implemented design requirements; automated browser/axe coverage is pending |
| Visitors can distinguish observed, simulated, and mission media | Content labels are present; validate with nontechnical usability testing |
