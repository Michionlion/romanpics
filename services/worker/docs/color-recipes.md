# Roman WFI display-color recipes

Roman observes through filters; those measurements do not arrive as literal display
RGB. RomanPics labels every composite as a representational-color image and stores
the recipe name and renderer version with it. These mappings are starting points for
consistent browsing, not official NASA/STScI color prescriptions.

Every source band is independently sigma-clipped, combined with other available
bands assigned to that channel, and passed through the same asinh stretch. A recipe
fails if any RGB channel has no available source band instead of silently inventing
data. `R062`, `Z087`, `Y106`, `J129`, `W146`, and `H158` are accepted aliases for the
corresponding `F` identifiers.

| Recipe | Blue | Green | Red | Intended use |
| --- | --- | --- | --- | --- |
| `roman-wide` | F062, F087 | F106, F129, F146 | F158, F184, F213 | Broad public composites with many WFI bands |
| `roman-near-ir` | F106, F129 | F146, F158 | F184, F213 | Fields without the shortest filters |
| `roman-three-band` | F087 | F129 | F184 | Simple three-band comparison |

The deterministic renderer is identified as `romanpics-preview-v1`. Its content hash
covers the canonical array values, recipe name, sizes, stretch parameters, and WebP
settings. Changing a rendering decision creates new filenames rather than mutating an
old cached preview.

The default display transform is:

1. remove NaN/infinite values from statistics;
2. iterate a 3-sigma clip three times;
3. clamp to the clipped minimum and maximum;
4. map to `[0, 1]` with `asinh(10x) / asinh(10)`;
5. resize the long edge to exactly 320 or 768 pixels with Lanczos;
6. encode deterministic metadata-free RGB WebP at quality 82/method 6.

If formal Roman outreach processing guidance changes, add a new version or recipe;
do not alter an existing named recipe in place.
