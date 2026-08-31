"""Deterministic astronomy preview rendering.

The renderer works from arrays, FITS files, and ASDF files. It never needs to retain
an upstream science product after rendering; :meth:`render_bytes` and the remote
fetcher's context manager both remove temporary inputs in ``finally`` blocks.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

FILTER_ALIASES = {
    "R062": "F062",
    "Z087": "F087",
    "Y106": "F106",
    "J129": "F129",
    "W146": "F146",
    "H158": "F158",
    "F062": "F062",
    "F087": "F087",
    "F106": "F106",
    "F129": "F129",
    "F146": "F146",
    "F158": "F158",
    "F184": "F184",
    "F213": "F213",
}


@dataclass(frozen=True)
class ColorRecipe:
    """A transparent, reproducible mapping of observed filters to display RGB."""

    name: str
    red: tuple[str, ...]
    green: tuple[str, ...]
    blue: tuple[str, ...]
    description: str


COLOR_RECIPES: dict[str, ColorRecipe] = {
    "roman-wide": ColorRecipe(
        name="roman-wide",
        red=("F158", "F184", "F213"),
        green=("F106", "F129", "F146"),
        blue=("F062", "F087"),
        description="A broad short-to-long wavelength mapping for public WFI composites.",
    ),
    "roman-near-ir": ColorRecipe(
        name="roman-near-ir",
        red=("F184", "F213"),
        green=("F146", "F158"),
        blue=("F106", "F129"),
        description="A near-infrared mapping for fields without the two shortest filters.",
    ),
    "roman-three-band": ColorRecipe(
        name="roman-three-band",
        red=("F184",),
        green=("F129",),
        blue=("F087",),
        description="A simple long/middle/short three-band mapping.",
    ),
}


@dataclass(frozen=True)
class RenderConfig:
    sizes: tuple[int, ...] = (320, 768)
    sigma: float = 3.0
    clip_iterations: int = 3
    asinh_strength: float = 10.0
    webp_quality: int = 82
    webp_method: int = 6

    def __post_init__(self) -> None:
        if not self.sizes or any(size <= 0 for size in self.sizes):
            raise ValueError("sizes must contain positive pixel lengths")
        if self.sigma <= 0 or self.clip_iterations < 1 or self.asinh_strength <= 0:
            raise ValueError("stretch parameters must be positive")
        if not 0 <= self.webp_quality <= 100 or not 0 <= self.webp_method <= 6:
            raise ValueError("invalid WebP encoder settings")

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            {
                "sizes": sorted(set(self.sizes)),
                "sigma": self.sigma,
                "clip_iterations": self.clip_iterations,
                "asinh_strength": self.asinh_strength,
                "webp_quality": self.webp_quality,
                "webp_method": self.webp_method,
                "renderer": 1,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()


@dataclass(frozen=True)
class RenderedPreview:
    size: int
    width: int
    height: int
    digest: str
    path: Path


def _finite_float_array(array: np.ndarray | Sequence[Sequence[float]]) -> np.ndarray:
    result = np.asarray(array, dtype=np.float64)
    result = np.squeeze(result)
    if result.ndim != 2:
        raise ValueError(f"expected a two-dimensional science array, got shape {result.shape}")
    if result.size == 0:
        raise ValueError("cannot render an empty array")
    return result


def sigma_clipped_limits(
    array: np.ndarray | Sequence[Sequence[float]], sigma: float = 3.0, iterations: int = 3
) -> tuple[float, float]:
    """Return deterministic low/high display limits using iterative sigma clipping."""

    values = _finite_float_array(array)
    sample = values[np.isfinite(values)]
    if sample.size == 0:
        return 0.0, 1.0

    clipped = sample
    for _ in range(iterations):
        median = float(np.median(clipped))
        standard_deviation = float(np.std(clipped))
        if not math.isfinite(standard_deviation) or standard_deviation == 0:
            break
        keep = np.abs(clipped - median) <= sigma * standard_deviation
        next_clipped = clipped[keep]
        if next_clipped.size == 0 or next_clipped.size == clipped.size:
            break
        clipped = next_clipped

    low = float(np.min(clipped))
    high = float(np.max(clipped))
    if not math.isfinite(low) or not math.isfinite(high) or high <= low:
        center = low if math.isfinite(low) else 0.0
        return center, center + 1.0
    return low, high


def stretch_array(
    array: np.ndarray | Sequence[Sequence[float]],
    *,
    sigma: float = 3.0,
    iterations: int = 3,
    asinh_strength: float = 10.0,
) -> np.ndarray:
    """Map a science array to uint8 with a sigma-clipped asinh stretch."""

    values = _finite_float_array(array)
    low, high = sigma_clipped_limits(values, sigma=sigma, iterations=iterations)
    finite = np.nan_to_num(values, nan=low, posinf=high, neginf=low)
    normalized = np.clip((finite - low) / (high - low), 0.0, 1.0)
    stretched = np.arcsinh(asinh_strength * normalized) / np.arcsinh(asinh_strength)
    return np.rint(stretched * 255.0).astype(np.uint8)


def _canonical_filter(name: str) -> str:
    key = name.strip().upper()
    return FILTER_ALIASES.get(key, key)


def compose_rgb(
    filter_arrays: Mapping[str, np.ndarray],
    recipe: str | ColorRecipe = "roman-wide",
    *,
    sigma: float = 3.0,
    iterations: int = 3,
    asinh_strength: float = 10.0,
) -> np.ndarray:
    """Create an RGB display array, averaging available bands assigned per channel."""

    selected = COLOR_RECIPES[recipe] if isinstance(recipe, str) else recipe
    canonical = {
        _canonical_filter(name): _finite_float_array(value) for name, value in filter_arrays.items()
    }
    if not canonical:
        raise ValueError("at least one filter array is required")
    shapes = {array.shape for array in canonical.values()}
    if len(shapes) != 1:
        raise ValueError("all filter arrays must have the same shape")

    channels: list[np.ndarray] = []
    missing: list[str] = []
    for channel_name, bands in (
        ("red", selected.red),
        ("green", selected.green),
        ("blue", selected.blue),
    ):
        available = [
            canonical[_canonical_filter(band)]
            for band in bands
            if _canonical_filter(band) in canonical
        ]
        if not available:
            missing.append(channel_name)
            channels.append(np.zeros(next(iter(shapes)), dtype=np.uint8))
            continue
        combined = np.mean(np.stack(available, axis=0), axis=0)
        channels.append(
            stretch_array(
                combined,
                sigma=sigma,
                iterations=iterations,
                asinh_strength=asinh_strength,
            )
        )
    if missing:
        raise ValueError(f"recipe {selected.name!r} has no source bands for: {', '.join(missing)}")
    return np.stack(channels, axis=-1)


def _array_digest(array: np.ndarray, config: RenderConfig, recipe_name: str | None) -> str:
    canonical = np.asarray(array)
    if canonical.dtype.kind == "f":
        canonical = np.nan_to_num(
            canonical.astype("<f4"), nan=0.0, posinf=3.4028235e38, neginf=-3.4028235e38
        )
    else:
        canonical = canonical.astype(canonical.dtype.newbyteorder("<"), copy=False)
    hasher = hashlib.sha256()
    hasher.update(b"romanpics-preview-v1\0")
    hasher.update(str(canonical.shape).encode())
    hasher.update(canonical.tobytes(order="C"))
    hasher.update(config.canonical_bytes())
    hasher.update((recipe_name or "monochrome").encode())
    return hasher.hexdigest()


def _find_first_array(value: Any) -> np.ndarray | None:
    if isinstance(value, np.ndarray) and value.ndim >= 2:
        return value
    if isinstance(value, Mapping):
        for key in sorted(value, key=str):
            found = _find_first_array(value[key])
            if found is not None:
                return found
    if isinstance(value, (list, tuple)):
        for item in value:
            found = _find_first_array(item)
            if found is not None:
                return found
    return None


def _lookup_tree(tree: Any, key: str) -> Any:
    current = tree
    for part in key.split("."):
        current = current[part] if isinstance(current, Mapping) else getattr(current, part)
    return current


class ThumbnailRenderer:
    """Render reproducible, content-addressed WebP previews."""

    def __init__(self, config: RenderConfig | None = None):
        self.config = config or RenderConfig()

    def render_array(
        self,
        array: np.ndarray,
        output_dir: str | Path,
        *,
        digest_source: np.ndarray | None = None,
        recipe_name: str | None = None,
    ) -> list[RenderedPreview]:
        source = np.asarray(array)
        if source.ndim == 2:
            display = stretch_array(
                source,
                sigma=self.config.sigma,
                iterations=self.config.clip_iterations,
                asinh_strength=self.config.asinh_strength,
            )
            display = np.stack((display, display, display), axis=-1)
        elif source.ndim == 3 and source.shape[-1] in (3, 4):
            display = np.clip(source[..., :3], 0, 255).astype(np.uint8)
        else:
            raise ValueError("render_array accepts a 2-D array or an RGB/RGBA array")

        digest = _array_digest(
            digest_source if digest_source is not None else source, self.config, recipe_name
        )
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        image = Image.fromarray(display, mode="RGB")
        previews: list[RenderedPreview] = []
        for size in sorted(set(self.config.sizes)):
            ratio = size / max(image.size)
            dimensions = tuple(max(1, int(round(dimension * ratio))) for dimension in image.size)
            resized = image.resize(dimensions, resample=Image.Resampling.LANCZOS, reducing_gap=3.0)
            path = destination / f"{digest[:24]}-{size}.webp"
            buffer = io.BytesIO()
            resized.save(
                buffer,
                format="WEBP",
                quality=self.config.webp_quality,
                method=self.config.webp_method,
                exact=True,
                exif=b"",
                xmp=b"",
            )
            payload = buffer.getvalue()
            if not path.exists() or path.read_bytes() != payload:
                path.write_bytes(payload)
            previews.append(
                RenderedPreview(
                    size=size,
                    width=resized.width,
                    height=resized.height,
                    digest=digest,
                    path=path,
                )
            )
        return previews

    def render_filters(
        self,
        filter_arrays: Mapping[str, np.ndarray],
        output_dir: str | Path,
        *,
        recipe: str = "roman-wide",
    ) -> list[RenderedPreview]:
        display = compose_rgb(
            filter_arrays,
            recipe,
            sigma=self.config.sigma,
            iterations=self.config.clip_iterations,
            asinh_strength=self.config.asinh_strength,
        )
        canonical_layers = [
            np.asarray(filter_arrays[key], dtype=np.float32)
            for key in sorted(filter_arrays, key=lambda item: _canonical_filter(item))
        ]
        digest_source = np.stack(canonical_layers, axis=0)
        return self.render_array(
            display, output_dir, digest_source=digest_source, recipe_name=recipe
        )

    def read_science_array(self, source: str | Path, *, array_key: str | None = None) -> np.ndarray:
        path = Path(source)
        suffixes = "".join(path.suffixes).lower()
        if suffixes.endswith((".fits", ".fit", ".fts", ".fits.gz")):
            from astropy.io import fits

            with fits.open(path, memmap=False) as hdus:
                if array_key is not None:
                    selector: int | str = int(array_key) if array_key.isdigit() else array_key
                    data = hdus[selector].data
                    if data is None:
                        raise ValueError(f"FITS HDU {array_key!r} has no data")
                    return np.asarray(data)
                for hdu in hdus:
                    if hdu.data is not None and np.asarray(hdu.data).ndim >= 2:
                        return np.asarray(hdu.data)
            raise ValueError("no two-dimensional FITS image HDU found")
        if suffixes.endswith(".asdf"):
            import asdf

            with asdf.open(path, lazy_load=False) as document:
                data = (
                    _lookup_tree(document.tree, array_key)
                    if array_key
                    else _find_first_array(document.tree)
                )
                if data is None:
                    raise ValueError("no two-dimensional ASDF array found")
                return np.array(data, copy=True)
        raise ValueError(f"unsupported science product extension: {path.name}")

    def render_file(
        self, source: str | Path, output_dir: str | Path, *, array_key: str | None = None
    ) -> list[RenderedPreview]:
        return self.render_array(self.read_science_array(source, array_key=array_key), output_dir)

    def render_bytes(
        self,
        payload: bytes,
        output_dir: str | Path,
        *,
        suffix: str,
        array_key: str | None = None,
        temporary_parent: str | Path | None = None,
    ) -> list[RenderedPreview]:
        """Render bytes via a temporary source that is always recursively removed."""

        with tempfile.TemporaryDirectory(
            prefix="romanpics-source-", dir=temporary_parent
        ) as temp_dir:
            source = Path(temp_dir) / f"source{suffix}"
            source.write_bytes(payload)
            return self.render_file(source, output_dir, array_key=array_key)
