from __future__ import annotations

import io
from pathlib import Path

import asdf
import numpy as np
from astropy.io import fits
from PIL import Image

from romanpics_worker.rendering import (
    COLOR_RECIPES,
    RenderConfig,
    ThumbnailRenderer,
    compose_rgb,
    stretch_array,
)


def synthetic_field(height: int = 50, width: int = 100) -> np.ndarray:
    y, x = np.mgrid[-1 : 1 : complex(height), -1 : 1 : complex(width)]
    field = 50 * np.exp(-((x - 0.2) ** 2 + (y + 0.1) ** 2) / 0.03)
    field += 10 * np.exp(-((x + 0.5) ** 2 + (y - 0.3) ** 2) / 0.1)
    field += x + y
    field[0, 0] = np.nan
    field[-1, -1] = np.inf
    return field.astype(np.float32)


def test_default_renderer_makes_exact_long_edge_sizes_and_stable_bytes(tmp_path: Path) -> None:
    renderer = ThumbnailRenderer()
    first = renderer.render_array(synthetic_field(), tmp_path / "first")
    second = renderer.render_array(synthetic_field(), tmp_path / "second")

    assert [preview.size for preview in first] == [320, 768]
    assert [(preview.width, preview.height) for preview in first] == [(320, 160), (768, 384)]
    assert [preview.digest for preview in first] == [preview.digest for preview in second]
    assert [preview.path.read_bytes() for preview in first] == [
        preview.path.read_bytes() for preview in second
    ]
    assert first[0].path.name.endswith("-320.webp")
    with Image.open(first[0].path) as image:
        assert image.mode == "RGB"
        assert image.format == "WEBP"


def test_fits_and_asdf_arrays_render_and_temporary_bytes_are_cleaned(tmp_path: Path) -> None:
    field = synthetic_field(20, 30)
    fits_path = tmp_path / "field.fits"
    fits.PrimaryHDU(field).writeto(fits_path)
    asdf_path = tmp_path / "field.asdf"
    asdf.AsdfFile({"roman": {"data": field}}).write_to(asdf_path)
    renderer = ThumbnailRenderer(RenderConfig(sizes=(32,)))

    fits_result = renderer.render_file(fits_path, tmp_path / "fits-output")
    asdf_result = renderer.render_file(asdf_path, tmp_path / "asdf-output", array_key="roman.data")
    assert fits_result[0].digest == asdf_result[0].digest

    temporary_parent = tmp_path / "temporary"
    temporary_parent.mkdir()
    renderer.render_bytes(
        fits_path.read_bytes(),
        tmp_path / "bytes-output",
        suffix=".fits",
        temporary_parent=temporary_parent,
    )
    assert list(temporary_parent.iterdir()) == []


def test_stretch_handles_nonfinite_and_constant_arrays() -> None:
    stretched = stretch_array(np.array([[np.nan, np.inf], [-np.inf, 4.0]]))
    assert stretched.dtype == np.uint8
    assert stretched.shape == (2, 2)
    constant = stretch_array(np.full((3, 4), 7.0))
    assert np.array_equal(constant, np.zeros((3, 4), dtype=np.uint8))


def test_documented_rgb_recipe_composes_aliases_and_is_renderable(tmp_path: Path) -> None:
    base = synthetic_field(12, 16)
    rgb = compose_rgb(
        {
            "Z087": base,
            "J129": np.roll(base, 1, axis=0),
            "F184": np.roll(base, 2, axis=1),
        },
        "roman-three-band",
    )
    assert rgb.shape == (12, 16, 3)
    assert rgb.dtype == np.uint8
    output = ThumbnailRenderer(RenderConfig(sizes=(24,))).render_filters(
        {"F087": base, "F129": base + 1, "F184": base + 2},
        tmp_path,
        recipe="roman-three-band",
    )
    assert output[0].path.exists()
    assert set(COLOR_RECIPES) == {"roman-wide", "roman-near-ir", "roman-three-band"}


def test_asdf_bytes_round_trip_without_leaking_a_source(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    asdf.AsdfFile({"data": synthetic_field(8, 8)}).write_to(buffer)
    parent = tmp_path / "scratch"
    parent.mkdir()
    ThumbnailRenderer(RenderConfig(sizes=(16,))).render_bytes(
        buffer.getvalue(), tmp_path / "output", suffix=".asdf", temporary_parent=parent
    )
    assert not any(parent.iterdir())
