# Roman imagery and archive research

Research snapshot: **August 30, 2026**.

## Mission status

Roman launched on August 30, 2026 and is traveling toward the Sun–Earth L2
region. There are no flight-science images yet. NASA expects first imagery in
early 2027 after roughly three months of travel, deployment, calibration, and
commissioning.

Primary references:

- [NASA Roman mission page](https://science.nasa.gov/mission/roman-space-telescope/)
- [NASA: nine things to know about Roman](https://science.nasa.gov/missions/roman-space-telescope/9-things-to-know-about-nasas-nancy-grace-roman-space-telescope/)
- [STScI's current first-two-years observing plan](https://roman-docs.stsci.edu/roman-community-defined-surveys/roman-observations-in-the-first-two-years-of-science-operations)

The launch-era catalog therefore needs four explicit content classes:

- `MISSION_PHOTO` — real photography of people, launch, and hardware;
- `VISUALIZATION` — explanatory graphics or artist concepts;
- `SIMULATION` — synthetic science content, never observed by Roman;
- `GROUND_TEST` — instrument or detector data produced on Earth.

`FLIGHT_SCIENCE` becomes available only after operations begin.

## Public sources available now

### NASA Image and Video Library

Best source for mission photography and outreach assets. The documented API
supports:

- `GET https://images-api.nasa.gov/search`
- `GET https://images-api.nasa.gov/asset/{nasa_id}`
- `GET https://images-api.nasa.gov/metadata/{nasa_id}`

Search results provide NASA IDs, dates, titles, descriptions, keywords, and a
preview. Asset manifests expose original and smaller hosted renditions. These
can be shown directly without storing the underlying files.

Source: [NASA Images API documentation](https://images.nasa.gov/docs/images.nasa.gov_api_docs.pdf)

### NASA Scientific Visualization Studio (SVS)

Best source for public-facing Roman simulations, explainers, stills, and
animations. SVS documents free JSON endpoints:

- `GET https://svs.gsfc.nasa.gov/api/search/?search=Roman`
- `GET https://svs.gsfc.nasa.gov/api/{id}/`

Detail records include the source page, `main_image`, pixel dimensions, alt
text, credits, and multiple media renditions. Smaller `searchweb` assets are
particularly useful as remote thumbnails.

Sources: [SVS API help](https://svs.gsfc.nasa.gov/help/) and the
[Roman SVS gallery](https://svs.gsfc.nasa.gov/gallery/roman/)

### IPAC/IRSA simulations

These are scientifically valuable but usually not browser-ready:

- [OpenUniverse2024 overview](https://irsa.ipac.caltech.edu/data/theory/openuniverse2024/overview.html)
  and [download inventory](https://irsa.ipac.caltech.edu/data/theory/openuniverse2024/download.html)
  contain Roman WFI simulations in FITS, Parquet, and HDF5.
- [IRSA cloud access](https://irsa.ipac.caltech.edu/cloud_access/) documents
  anonymous `us-east-1` access to `s3://nasa-irsa-simulations`, including
  `openuniverse2024/roman/preview` and `openuniverse2024/roman/full`. “Preview”
  is a reduced dataset, not necessarily a JPEG.
- [Roman Data Challenge 2](https://roman.ipac.caltech.edu/page/roman-dc2-simulated-images)
  provides 20 square degrees of synthetic four-band imaging, truth catalogs,
  segmentation maps, and PSFs.
- [IRSA's Atlas program interface](https://irsa.ipac.caltech.edu/applications/Atlas/AtlasProgramInterface.html)
  can locate DC2 products through XML queries, but it is not a dependable
  consumer-thumbnail API.
- IPAC also hosts [Coronagraph simulations](https://roman.ipac.caltech.edu/page/coronagraph-public-images-html),
  [supernova survey simulations](https://roman.ipac.caltech.edu/page/sn-survey-image-sim-html),
  and [galaxy redshift survey simulations](https://roman.ipac.caltech.edu/page/galaxy-redshift-survey-sim-html).

Ingestion should start from a reviewed manifest for these collections rather
than scraping their presentation pages.

### MAST preflight material

- [WFI Triplet Test Data](https://archive.stsci.edu/missions-and-data/roman/wfi-triplet-test-data)
  are large laboratory detector files. They are ground-test data, not sky images.
- The [Illustris Roman simulated deep fields](https://archive.stsci.edu/hlsp/illustris)
  combine downloadable FITS products with useful curated previews.

## What MAST will publish

MAST is the authoritative archive for Roman science data. Roman WFI science
products are planned to be public without an exclusive-access period.

| Level | Target availability | Typical product | Gallery relevance |
| --- | --- | --- | --- |
| L1 | within 24 hours | uncalibrated ramp, `_uncal.asdf` | technical download only |
| L2 | within 48 hours | calibrated detector image, `_cal.asdf` | group under observation |
| prompt L3 | within 5 days after inputs arrive | coadd/mosaic, `_coadd.asdf` | first good automatic gallery candidate |
| prompt L4 | within 7 days | catalog/segmentation/spectra | enrich search and labels |
| data release | survey-dependent, roughly every 6–12 months | preserved/reprocessed L3/L4 | preferred canonical long-term record |

Sources:

- [Roman Archive in MAST](https://roman-docs.stsci.edu/data-handbook/accessing-wfi-data/the-roman-archive-in-mast)
- [WFI data levels and formats](https://roman-docs.stsci.edu/data-handbook/wfi-data-levels-and-products)
- [Prompt products](https://roman-docs.stsci.edu/data-handbook/wfi-data-levels-and-products/prompt-products)
- [Data releases](https://roman-docs.stsci.edu/data-handbook/wfi-data-levels-and-products/data-releases)
- [WFI pipeline policy](https://roman-docs.stsci.edu/data-handbook/roman-wfi-data-pipelines)
- [Coronagraph data format and access](https://roman-docs.ipac.caltech.edu/data-handbook/coronagraph-instrument-data/roman-coronagraph-data-format-and-access)

### Persistence caveats

- Prompt products are not versioned. Reprocessing can overwrite them.
- Selected prompt L3/L4 products may later be removed after a retention period.
- Prompt L4 files are downloadable, but are not inserted into MAST's searchable
  catalog database.
- Data-release versions are preserved and are safer canonical targets.
- L0 packet data are restricted.
- Most products are ASDF or Parquet, not JPEG/PNG. Multi-filter color imagery
  requires deliberate rendering and color mapping.

RomanPics must keep its own immutable item IDs and record upstream version,
processing state, checksums/ETags when supplied, and supersession relationships.

## Future access and previews

STScI plans access through Roman Mission Search, `astroquery.mast`, the MAST/Data
Access APIs, cloud URIs, future Virtual Observatory services, and a planned WFI
cutout service. Roman data live in AWS `us-east-1`, where STScI recommends
streaming or in-cloud work for large requests.

- [Accessing WFI data](https://roman-docs.stsci.edu/data-handbook/accessing-wfi-data)
- [Roman cloud access](https://roman-docs.stsci.edu/data-handbook/accessing-wfi-data/the-roman-archive-in-mast/cloud-access)
- [Roman Mission Search](https://mast.stsci.edu/search/ui/#/roman)
- [Generic MAST API](https://mast.stsci.edu/api/v0/)

The current documented access matrix has an important gap: the MAST Portal and
Roman Mission Search list previews, while `astroquery.mast` and the MAST API do
not document preview access. Private-looking Roman Mission Search endpoints are
not a stable API and must not be an MVP dependency.

[MAST subscriptions](https://archive.stsci.edu/contents/newsletters/may-2026/mast-subscriptions)
may become a useful ingestion trigger because they can send periodic JSON lists
of new Roman files.

## Thumbnail decision

Resolve previews in this order:

1. upstream web rendition explicitly supplied by NASA Images or SVS;
2. a documented MAST preview or cutout when STScI exposes one;
3. an official outreach composite that points back to the archive record;
4. a small, deterministic site-generated derivative from a cutout or L3 mosaic.

For site-generated derivatives, download only what is needed, delete temporary
source bytes, store 320px/768px WebP outputs under content-addressed names, and
record the stretch/color recipe. Never expose a general-purpose URL-to-image
proxy; source hosts and redirects must be allowlisted to avoid SSRF.

## Rights and provenance

Do not apply a blanket media license. NASA assets generally support educational
and informational use, but credits and third-party restrictions still matter.
MAST says most holdings are public domain while some community high-level
products are CC BY 4.0 or have collection-specific restrictions.

- [NASA images and media guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/)
- [MAST data-use policy](https://archive.stsci.edu/publishing/data-use)
- [Roman acknowledgment guidance](https://archive.stsci.edu/publishing/mission-acknowledgements)

Every catalog record should therefore retain its source URL, credit line, rights
statement/URL, and any required acknowledgment.

