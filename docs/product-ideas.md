# Product ideas and readiness matrix

RomanPics can be useful before first light without pretending simulations are
observations. The repository implements the interaction shell for the ideas
that do not yet have flight data and keeps the data-dependent pieces gated.

| Idea | What exists now | Production gate |
| --- | --- | --- |
| Explore and natural-language search | Search, content labels, filters, top/new/trending, paginated/shareable URLs | Grow the index through scheduled source syncs |
| Similarity neighborhoods | Item/group votes, explainable fixture groups, hashes, embeddings, class-separated k-NN and stable cluster reconciliation | Run the worker against a representative corpus and review automatic labels |
| Mission journey | Launch-to-first-light timeline and editorial collections | Connect only to an authoritative mission-status source |
| Sky search | Accessible RA/Dec/radius form and empty-state coverage view; API cone query | Public Roman footprints and measured HEALPix strategy |
| Same field, different filters | Accessible comparison slider | Two or more aligned public products for one observation family |
| Infrared color lab | Interactive educational color-channel composer | Reviewed WFI filter recipes and real aligned L3 inputs |
| Field-of-view comparison | Interactive Roman/Hubble/Webb scale explainer | Reviewed footprints and image-registration examples |
| Surprise me | Mood/subject modes with a no-store API response | Optional richer reviewed tags |
| Feeds and embeds | RSS, Atom, sitemap, robots, and a small iframe-friendly gallery card | Public hostname and stable cache policy |
| Source transparency | Public status page, run records, link checker, provenance and rights on item pages | Scheduler and alert destination |
| First-light watch | Fixture-tested prompt overwrite/final supersession and an operator checklist | Supported MAST search/preview contract and shadow-run signoff |

## High-value next additions after real observations arrive

- A time-domain blink view for repeat visits, with a reduced-motion alternative.
- Observation-family pages that collect detector products without turning every
  L1/L2 file into a consumer gallery card.
- Cross-mission links by coordinate to Hubble, Webb, Euclid, and Rubin archives.
- Personal saved collections, with passkeys or email only if cross-device sync
  becomes valuable; browsing and voting should remain account-free.
- Reviewed public tags and short curator notes, separated from authoritative
  archive metadata and never used to invent scientific identifications.
- A “provenance receipt” download containing source ID, processing version,
  product links, credit, rights, and any site-generated preview recipe.

The project should resist expensive novelty until traffic or catalog size makes
it necessary: PostgreSQL search before Elasticsearch, a database jobs table
before Redis, and VPS preview storage before adding object storage.
