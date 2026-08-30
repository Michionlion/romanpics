# RomanPics

An unofficial, open-source explorer for discovering imagery connected to NASA's
Nancy Grace Roman Space Telescope and following those images back to their
authoritative source.

> RomanPics is independent and is not affiliated with or endorsed by NASA,
> STScI, or IPAC. Upstream images and data keep their original credits and terms.

## Why this exists

Roman launched on August 30, 2026. There are no flight-science images yet;
NASA expects the first images in early 2027 after the observatory reaches L2 and
completes commissioning. In the meantime, NASA and its partners already publish
excellent mission photography, visualizations, ground-test data, and science
simulations.

RomanPics aims to make all of that approachable now, then become a friendly
discovery layer over the public Roman archive once science operations begin.
It will catalog and link to originals rather than mirror multi-gigabyte science
products.

## Current prototype

The launch-era prototype includes:

- search and plain-language category filters;
- direct links to NASA-hosted originals and source pages;
- unambiguous labels for mission photos, visualizations, and simulations;
- a “Surprise me” path for casual exploration;
- separate local upvotes for pictures and similarity groups; and
- a responsive, keyboard-accessible gallery designed for non-specialists.

Votes currently live only in browser memory. The ingestion service, persistent
votes, public API, and automatic similarity pipeline are designed but not yet
implemented.

## Source strategy

| Stage | Authoritative source | What RomanPics uses |
| --- | --- | --- |
| Now | NASA Image and Video Library | Mission, hardware, launch, and outreach records with hosted renditions |
| Now | NASA Scientific Visualization Studio | Simulations, explainers, animations, credits, alt text, and web-sized stills |
| Now | IPAC/IRSA and MAST | Clearly marked simulations and ground-test datasets |
| Science operations | MAST Roman archive | Public WFI/Coronagraph observations, metadata, products, and supported previews |

See [Roman data sources](docs/roman-data-sources.md) for the evidence and current
limitations.

## Product and system shape

RomanPics is a metadata-and-preview index, not a data mirror:

```text
NASA Images ─┐
NASA SVS ────┼─> source adapters ─> normalized catalog ─> search/API ─> web gallery
IPAC/IRSA ───┤                           │                    │
MAST Roman ──┘                           ├─> preview resolver ├─> picture votes
                                           └─> embeddings      └─> group votes
```

The long-term production plan uses PostgreSQL with full-text search and pgvector,
a small API, and one background worker. Original files remain upstream. A source
rendition is preferred; a small site-generated derivative is created only when
an official preview or cutout is unavailable.

- [Architecture and API scope](docs/architecture.md)
- [OpenAPI draft](docs/openapi.yaml)
- [Phased roadmap](docs/roadmap.md)

## Run it locally

Requirements: Node.js 22.13 or newer.

```bash
npm ci
npm run dev
```

Then open `http://localhost:3000`.

Useful checks:

```bash
npm run build
npm run lint
```

## Hosting direction

The cheapest sensible production shape is the existing VPS edge plus an app
container, API/worker, and PostgreSQL. The nearby edge stack is Nginx + Certbot,
not Traefik, so any VPS deployment should integrate with that actual setup.

Netlify remains useful for frontend-only previews, but ingestion, thumbnail
rendering, embeddings, and the database should stay on the VPS. No production
VPS or Netlify deployment is included in this initial repository.

## Contributing

Issues and pull requests are welcome. Please preserve three invariants:

1. Every item links to an authoritative source and carries its credit/rights data.
2. Simulated, ground-test, outreach, and flight-science content are never conflated.
3. RomanPics does not routinely store or proxy original science products.

See [CONTRIBUTING.md](CONTRIBUTING.md) before adding a new source adapter.

## License and media

The application code and project-authored documentation are licensed under the
[MIT License](LICENSE). That license does **not** cover third-party imagery or
data linked from the catalog. See [NOTICE](NOTICE) and each source record for
credits and use terms.

## Primary references

- [NASA Roman mission status](https://science.nasa.gov/mission/roman-space-telescope/)
- [Roman in MAST](https://archive.stsci.edu/missions-and-data/roman)
- [Roman archive documentation](https://roman-docs.stsci.edu/data-handbook/accessing-wfi-data/the-roman-archive-in-mast)
- [NASA Images API](https://images.nasa.gov/docs/images.nasa.gov_api_docs.pdf)
- [NASA SVS API](https://svs.gsfc.nasa.gov/help/)

