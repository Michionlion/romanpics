# Contributing to RomanPics

Thanks for helping make Roman imagery easier to explore.

## Before opening a pull request

```bash
npm ci
npm run build
npm run lint
```

Keep changes focused and explain user-visible behavior in the pull request.

## Adding catalog content

Every record must include:

- a stable upstream provider and external ID;
- an authoritative source/detail URL;
- a direct original or archive-product URL when available;
- an explicit content class (`FLIGHT_SCIENCE`, `SIMULATION`, `GROUND_TEST`,
  `MISSION_PHOTO`, or `VISUALIZATION`);
- credit, rights text/URL, date, descriptive alt text, and preview dimensions;
- enough plain-language context to avoid overstating what the image shows.

Do not copy an upstream original into this repository. Prefer a provider-hosted
web rendition. Do not label a simulation, artist concept, ground test, or image
from another telescope as an observation made by Roman.

## Adding a source adapter

An adapter must:

1. use a documented API or a reviewed/versioned manifest;
2. preserve the raw source record and normalize behind the shared contract;
3. make discovery/upserts idempotent;
4. expose source freshness and per-record failures;
5. validate hosts, redirects, MIME types, and response-size limits;
6. preserve provenance, rights, version, and supersession state; and
7. include fixtures plus tests that do not require the live provider.

Never depend on undocumented portal endpoints without an isolated experiment
and an approved fallback.

## UX and accessibility

- Use plain language before archive terminology.
- Do not communicate content status by color alone.
- Keep controls keyboard accessible with visible focus.
- Use authoritative captions for alt text; do not invent object identities.
- Respect reduced motion and keep mobile image payloads small.

## Community features

Picture votes and similarity-group votes are intentionally distinct. Avoid any
ranking formula that rewards a group merely for containing more members. Changes
to clustering must preserve or explicitly archive voted group identities.

