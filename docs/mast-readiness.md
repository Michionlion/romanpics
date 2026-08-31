# First-light and MAST readiness checklist

RomanPics can prepare the integration now without binding itself to an
undocumented MAST portal endpoint. The production adapter remains behind the
same source contract as NASA Images, SVS, and reviewed manifests.

## Before flight-science ingestion is enabled

- Confirm the supported Roman search, product, preview, and cutout interfaces
  with the MAST Help Desk.
- Capture anonymized response fixtures for one L1, L2, prompt L3, prompt L4,
  data-release L3, superseded prompt product, and absent preview.
- Verify field meaning for observation/program IDs, optical element, footprint,
  pipeline version, release, created/modified times, checksum, and cloud URI.
- Confirm hotlink/cache behavior and attribution for archive previews.
- Establish which prompt L3 products make one useful public gallery item.
- Test a prompt-to-data-release migration without changing the RomanPics ID,
  slug, collection membership, group history, or votes.
- Run ingestion in shadow mode for at least one complete poll interval, compare
  counts with Mission Search, then enable publishing through editorial review.

## Fixture rules

Fixtures must be small, static, and stripped of credentials. Tests cover:

- identical replay is idempotent;
- overlapping watermarks do not duplicate records;
- a changed processing version updates the source record but preserves history;
- supersession links the new product and keeps the old record auditable;
- an empty partial response never marks the catalog deleted;
- missing or unsupported previews produce a render job only for an allowlisted,
  bounded L3 product;
- L1/L2 records appear as technical products under a grouped observation rather
  than individual consumer cards;
- malformed upstream records fail individually and leave the run resumable.

## Message for MAST support

> We are building an independent, open-source public discovery index for Roman.
> We retain normalized metadata and small thumbnails only, link every item back
> to MAST, and do not mirror science originals. Which documented API should a
> third-party client use for Roman observation/product search after first light?
> Will supported WFI preview or cutout URLs be available through the MAST API or
> astroquery, and what cache/hotlink limits and attribution should we follow?
