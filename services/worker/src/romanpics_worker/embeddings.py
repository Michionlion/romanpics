"""Pluggable visual and metadata embedding interfaces.

The deterministic providers have no model weights and are appropriate for local
development, contract tests, and initial grouping. OpenCLIP and SigLIP providers
are optional and lazy-loaded. Model downloads are never enabled by default.
"""

from __future__ import annotations

import hashlib
import io
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import numpy as np
from PIL import Image, ImageOps


def _normalize(vector: np.ndarray) -> np.ndarray:
    result = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(result))
    return result / norm if norm > 0 else result


def _feature_hash(features: Sequence[float], dimension: int, namespace: bytes) -> np.ndarray:
    output = np.zeros(dimension, dtype=np.float64)
    for index, value in enumerate(features):
        digest = hashlib.blake2b(
            namespace + index.to_bytes(8, "little"), digest_size=8, person=b"romanpics"
        ).digest()
        bucket = int.from_bytes(digest[:4], "little") % dimension
        sign = 1.0 if digest[4] & 1 else -1.0
        output[bucket] += sign * float(value)
    return _normalize(output)


def _as_rgb_image(source: bytes | str | Path | Image.Image | np.ndarray) -> Image.Image:
    if isinstance(source, Image.Image):
        return ImageOps.exif_transpose(source).convert("RGB")
    if isinstance(source, np.ndarray):
        array = np.asarray(source)
        if array.ndim == 2:
            finite = np.nan_to_num(array.astype(np.float64))
            minimum, maximum = float(np.min(finite)), float(np.max(finite))
            normalized = (
                np.zeros_like(finite)
                if maximum <= minimum
                else (finite - minimum) / (maximum - minimum)
            )
            uint8 = np.rint(np.clip(normalized, 0, 1) * 255).astype(np.uint8)
            return Image.fromarray(uint8, mode="L").convert("RGB")
        if array.ndim == 3 and array.shape[-1] in (3, 4):
            return Image.fromarray(np.clip(array[..., :3], 0, 255).astype(np.uint8), mode="RGB")
        raise ValueError("visual embedding expects a 2-D array or RGB/RGBA array")
    if isinstance(source, bytes):
        with Image.open(io.BytesIO(source)) as opened:
            return ImageOps.exif_transpose(opened).convert("RGB")
    with Image.open(source) as opened:
        return ImageOps.exif_transpose(opened).convert("RGB")


@runtime_checkable
class VisualEmbedder(Protocol):
    provider_name: str
    dimension: int

    def embed(self, image: bytes | str | Path | Image.Image | np.ndarray) -> np.ndarray: ...


@runtime_checkable
class MetadataEmbedder(Protocol):
    provider_name: str
    dimension: int

    def embed(self, metadata: Mapping[str, Any]) -> np.ndarray: ...


class DeterministicVisualEmbedder:
    """Small color/spatial/edge descriptor projected with stable feature hashing."""

    provider_name = "deterministic-visual-v1"

    def __init__(self, dimension: int = 96):
        if dimension < 16:
            raise ValueError("visual embedding dimension must be at least 16")
        self.dimension = dimension

    def embed(self, image: bytes | str | Path | Image.Image | np.ndarray) -> np.ndarray:
        rgb = (
            np.asarray(
                _as_rgb_image(image).resize((32, 32), Image.Resampling.LANCZOS), dtype=np.float64
            )
            / 255.0
        )
        features: list[float] = []

        # Global channel histograms retain coarse palette information.
        for channel in range(3):
            histogram, _ = np.histogram(rgb[..., channel], bins=16, range=(0.0, 1.0), density=False)
            features.extend((histogram / histogram.sum()).tolist())

        # An 8x8 spatial grid retains rough composition without memorizing pixels.
        features.extend(rgb.reshape(8, 4, 8, 4, 3).mean(axis=(1, 3)).reshape(-1).tolist())

        grayscale = rgb @ np.array([0.2126, 0.7152, 0.0722])
        horizontal = np.diff(grayscale, axis=1)
        vertical = np.diff(grayscale, axis=0)
        features.extend(
            [
                float(np.mean(grayscale)),
                float(np.std(grayscale)),
                float(np.mean(np.abs(horizontal))),
                float(np.mean(np.abs(vertical))),
            ]
        )
        return _feature_hash(features, self.dimension, b"visual-v1")


def _flatten_metadata(value: Any, prefix: str = "") -> list[tuple[str, str]]:
    if isinstance(value, Mapping):
        output: list[tuple[str, str]] = []
        for key in sorted(value, key=str):
            path = f"{prefix}.{key}" if prefix else str(key)
            output.extend(_flatten_metadata(value[key], path))
        return output
    if isinstance(value, (list, tuple, set, frozenset)):
        output = []
        for item in sorted(value, key=str):
            output.extend(_flatten_metadata(item, prefix))
        return output
    return [(prefix, str(value))]


class DeterministicMetadataEmbedder:
    """Signed feature-hashed tokens with stable ordering and no Python hash salt."""

    provider_name = "deterministic-metadata-v1"
    _tokens = re.compile(r"[\w.+-]+", flags=re.UNICODE)

    def __init__(self, dimension: int = 192):
        if dimension < 32:
            raise ValueError("metadata embedding dimension must be at least 32")
        self.dimension = dimension

    def embed(self, metadata: Mapping[str, Any]) -> np.ndarray:
        weighted_tokens: Counter[str] = Counter()
        for field, value in _flatten_metadata(metadata):
            normalized_field = field.casefold()
            normalized_value = value.casefold()
            weighted_tokens[f"field:{normalized_field}"] += 1
            weighted_tokens[f"pair:{normalized_field}={normalized_value}"] += 2
            words = self._tokens.findall(normalized_value)
            for word in words:
                weighted_tokens[f"word:{word}"] += 1
            for left, right in zip(words, words[1:], strict=False):
                weighted_tokens[f"bigram:{left}_{right}"] += 1

        vector = np.zeros(self.dimension, dtype=np.float64)
        for token, count in sorted(weighted_tokens.items()):
            digest = hashlib.blake2b(token.encode(), digest_size=8, person=b"romanmeta").digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[bucket] += sign * (1.0 + np.log(float(count)))
        return _normalize(vector)


class CombinedEmbedder:
    """Concatenate normalized visual and metadata vectors with explicit weights."""

    def __init__(
        self,
        visual: VisualEmbedder | None = None,
        metadata: MetadataEmbedder | None = None,
        *,
        visual_weight: float = 0.7,
        metadata_weight: float = 0.3,
    ):
        if visual_weight < 0 or metadata_weight < 0 or visual_weight + metadata_weight == 0:
            raise ValueError("embedding weights must be non-negative and not both zero")
        self.visual = visual or DeterministicVisualEmbedder()
        self.metadata = metadata or DeterministicMetadataEmbedder()
        self.visual_weight = visual_weight
        self.metadata_weight = metadata_weight
        self.dimension = self.visual.dimension + self.metadata.dimension
        self.provider_name = f"combined:{self.visual.provider_name}+{self.metadata.provider_name}"

    def embed(
        self, image: bytes | str | Path | Image.Image | np.ndarray, metadata: Mapping[str, Any]
    ) -> np.ndarray:
        return _normalize(
            np.concatenate(
                (
                    self.visual.embed(image) * self.visual_weight,
                    self.metadata.embed(metadata) * self.metadata_weight,
                )
            )
        )


class OpenCLIPVisualEmbedder:
    """Optional OpenCLIP provider.

    With the safe default ``allow_download=False``, callers must pass a local
    ``checkpoint_path``. Setting ``allow_download=True`` explicitly permits the
    upstream library to resolve its named pretrained weights.
    """

    provider_name = "openclip"

    def __init__(
        self,
        model_name: str = "ViT-B-32",
        *,
        pretrained: str = "laion2b_s34b_b79k",
        checkpoint_path: str | Path | None = None,
        allow_download: bool = False,
        device: str = "cpu",
    ):
        try:
            import open_clip
            import torch
        except ImportError as error:
            raise RuntimeError("install romanpics-worker[openclip] to use OpenCLIP") from error
        if not allow_download and checkpoint_path is None:
            raise ValueError("a local checkpoint_path is required unless allow_download=True")
        with torch.random.fork_rng():
            torch.manual_seed(0)
            model, _, preprocess = open_clip.create_model_and_transforms(
                model_name, pretrained=pretrained if allow_download else None
            )
        if checkpoint_path is not None:
            open_clip.load_checkpoint(model, str(checkpoint_path))
        self._torch = torch
        self._model = model.eval().to(device)
        self._preprocess = preprocess
        self._device = device
        self.dimension = int(model.visual.output_dim)
        self.provider_name = f"openclip:{model_name}:{pretrained}"

    def embed(self, image: bytes | str | Path | Image.Image | np.ndarray) -> np.ndarray:
        tensor = self._preprocess(_as_rgb_image(image)).unsqueeze(0).to(self._device)
        with self._torch.inference_mode():
            vector = self._model.encode_image(tensor).detach().cpu().numpy()[0]
        return _normalize(vector)


class SigLIPVisualEmbedder:
    """Optional Hugging Face SigLIP provider, local-files-only by default."""

    provider_name = "siglip"

    def __init__(
        self,
        model_name_or_path: str = "google/siglip-base-patch16-224",
        *,
        allow_download: bool = False,
        device: str = "cpu",
    ):
        try:
            import torch
            from transformers import AutoModel, AutoProcessor
        except ImportError as error:
            raise RuntimeError("install romanpics-worker[siglip] to use SigLIP") from error
        local_only = not allow_download
        self._processor = AutoProcessor.from_pretrained(
            model_name_or_path, local_files_only=local_only
        )
        self._model = (
            AutoModel.from_pretrained(model_name_or_path, local_files_only=local_only)
            .eval()
            .to(device)
        )
        self._torch = torch
        self._device = device
        projection = getattr(self._model.config, "projection_dim", None)
        vision_config = getattr(self._model.config, "vision_config", None)
        self.dimension = int(projection or vision_config.hidden_size)
        self.provider_name = f"siglip:{model_name_or_path}"

    def embed(self, image: bytes | str | Path | Image.Image | np.ndarray) -> np.ndarray:
        inputs = self._processor(images=_as_rgb_image(image), return_tensors="pt")
        inputs = {key: value.to(self._device) for key, value in inputs.items()}
        with self._torch.inference_mode():
            if hasattr(self._model, "get_image_features"):
                vector = self._model.get_image_features(**inputs)
            else:
                vector = self._model(**inputs).image_embeds
        return _normalize(vector.detach().cpu().numpy()[0])
