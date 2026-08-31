## What changed

<!-- Describe the visitor-facing or operational outcome. -->

## Catalog invariants

- [ ] Every new item has an authoritative source, credit, rights information,
      descriptive alt text, and an explicit content class.
- [ ] Simulations, ground tests, mission photos, visualizations, and flight
      science are not conflated.
- [ ] No original science product or provider secret was committed.
- [ ] Remote fetch behavior remains HTTPS-only, allowlisted, bounded, and
      independent of browser-supplied URLs.

## Verification

- [ ] Frontend checks pass.
- [ ] API and worker tests pass when those packages are affected.
- [ ] I tested keyboard use and the API-unavailable fallback for UI changes.
