# RomanPics roadmap

The roadmap is deliberately staged around the real mission timeline. Dates for
science operations can change; product gates matter more than calendar promises.

## Phase 0 — launch-era prototype (now)

- [x] Establish an independent project identity and public-source policy.
- [x] Build an interactive gallery concept with search, filters, source links,
  image votes, and group votes.
- [x] Research NASA Images, NASA SVS, IPAC/IRSA, and planned MAST access.
- [x] Draft the normalized model, public API, similarity approach, and hosting plan.
- [ ] Convert the curated records into a validated, checked-in source manifest.
- [ ] Add link, credit, content-class, and remote-image checks in CI.
- [ ] Ask the MAST Help Desk which preview/cutout surfaces are supported for
  third-party clients and what will be available at first light.

Exit gate: every preview record has a resolvable authoritative source, content
class, credit, and remote rendition; the UI makes no claim that simulations are
Roman observations.

## Phase 1 — launch-to-first-light MVP

- Implement `nasa_images`, `nasa_svs`, and reviewed `ipac_manifest` adapters.
- Add PostgreSQL schema, ingestion runs, idempotent upserts, and source status.
- Implement gallery list/detail routes and the read-only `/v1` API.
- Add top/new/trending sorts, facets, shareable searches, and pagination.
- Add editorial collections: Launch, Building Roman, What Roman May See.
- Persist anonymous picture and group votes with basic abuse controls.
- Add admin review for content class, title, plain-language summary, rights, and alt text.
- Add weekly outbound-link reconciliation and accessibility checks.

Exit gate: the site can rebuild its entire launch-era catalog from upstream
metadata/manifests and retains no upstream originals.

## Phase 2 — similarity and community

- Compute checksums and perceptual hashes for duplicate detection.
- Generate versioned visual embeddings and trusted metadata embeddings.
- Expose “More like this” and deterministic observation/source families.
- Run versioned clustering and preserve group identity across recomputation.
- Add group pages and community-selected representative images.
- Add lightweight moderation, vote audit tooling, Atom/RSS, and source-health UI.
- Consider optional passkey/email accounts for synced favorites.

Exit gate: clusters are explainable, stable enough to receive votes, and never mix
simulations or mission photography with flight-science imagery by accident.

## Phase 3 — first light and science operations

- Validate the production `mast_roman` adapter against real WFI/Coronagraph records.
- Prefer supported previews/cutouts and prompt L3 mosaics for gallery ingestion.
- Group L1/L2 detector products under observation-family detail pages.
- Record processing version, checksums/ETags, and prompt supersession state.
- Subscribe to new-file notifications when stable, with polling/reconciliation as fallback.
- Implement the bounded preview renderer only for items without an upstream rendition.
- Migrate canonical prompt items to preserved data-release products without losing
  URLs, votes, groups, or provenance.

Exit gate: new public observations become discoverable within one ingestion cycle,
and upstream replacement/removal never silently breaks a voted RomanPics item.

## Phase 4 — richer discovery

- Coordinate/footprint sky map and cone search.
- Same-sky, different-filter comparisons and accessible before/after sliders.
- Time-domain blink views and light-curve companions.
- Cross-mission coordinate links to Hubble, Webb, Euclid, and Rubin archives.
- Saved/shareable collections and reviewed community tags.
- Public API clients and a small embeddable gallery widget.
- “Surprise me” modes for object type, distance, survey, or visual mood.

## MVP success measures

- 100% of cards expose source, credit/rights, and content class.
- 0 original science products retained after processing.
- At least 95% of outbound asset/source links valid in the weekly check.
- Source freshness and degraded adapters visible.
- First gallery load roughly 1 MB or less on a typical mobile viewport.
- Keyboard navigation, reduced motion, and automated accessibility checks in CI.
- A nontechnical visitor can explain whether an image is observed, simulated, or
  mission photography after using the site.

