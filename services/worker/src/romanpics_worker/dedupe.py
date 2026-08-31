"""Exact and perceptual duplicate detection for public preview imagery."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np
from PIL import Image, ImageOps


@dataclass(frozen=True)
class ImageHashes:
    sha256: str
    phash: str


@dataclass(frozen=True)
class DuplicateMatch:
    item_id: str
    kind: str
    distance: int


def exact_hash(payload: bytes | bytearray | memoryview) -> str:
    return hashlib.sha256(payload).hexdigest()


def _open_image(
    source: bytes | bytearray | memoryview | str | Path | BinaryIO | Image.Image,
) -> Image.Image:
    if isinstance(source, Image.Image):
        return source.copy()
    if isinstance(source, (bytes, bytearray, memoryview)):
        return Image.open(io.BytesIO(bytes(source)))
    return Image.open(source)


def _dct_matrix(size: int) -> np.ndarray:
    coordinates = np.arange(size, dtype=np.float64)
    frequencies = coordinates[:, None]
    matrix = np.cos(np.pi * (2 * coordinates + 1) * frequencies / (2 * size))
    matrix[0, :] *= np.sqrt(1 / size)
    matrix[1:, :] *= np.sqrt(2 / size)
    return matrix


def perceptual_hash(
    source: bytes | bytearray | memoryview | str | Path | BinaryIO | Image.Image,
    *,
    hash_size: int = 8,
    high_frequency_factor: int = 4,
) -> str:
    """Compute a stable DCT pHash, represented as fixed-width hexadecimal."""

    if hash_size <= 1 or high_frequency_factor < 1:
        raise ValueError("invalid perceptual hash dimensions")
    sample_size = hash_size * high_frequency_factor
    with _open_image(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("L")
        pixels = np.asarray(
            image.resize((sample_size, sample_size), Image.Resampling.LANCZOS), dtype=np.float64
        )
    basis = _dct_matrix(sample_size)
    coefficients = basis @ pixels @ basis.T
    low_frequencies = coefficients[:hash_size, :hash_size].reshape(-1)
    threshold = float(np.median(low_frequencies[1:]))
    bits = low_frequencies > threshold
    bits[0] = False
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    width = (hash_size * hash_size + 3) // 4
    return f"{value:0{width}x}"


def hamming_distance(left: str, right: str) -> int:
    if len(left) != len(right):
        raise ValueError("hash strings must have the same width")
    return (int(left, 16) ^ int(right, 16)).bit_count()


def hashes_for_bytes(payload: bytes) -> ImageHashes:
    return ImageHashes(sha256=exact_hash(payload), phash=perceptual_hash(payload))


class DuplicateIndex:
    """A deliberately small exact+pHash index suitable for ingestion batches.

    Larger deployments can preserve this interface while replacing the linear pHash
    scan with a BK-tree or a database bit-distance index.
    """

    def __init__(self, *, perceptual_threshold: int = 6):
        if perceptual_threshold < 0:
            raise ValueError("perceptual_threshold must be non-negative")
        self.perceptual_threshold = perceptual_threshold
        self._hashes: dict[str, ImageHashes] = {}
        self._exact: dict[str, set[str]] = {}

    def add(self, item_id: str, hashes: ImageHashes) -> None:
        if item_id in self._hashes:
            self.remove(item_id)
        self._hashes[item_id] = hashes
        self._exact.setdefault(hashes.sha256, set()).add(item_id)

    def remove(self, item_id: str) -> None:
        hashes = self._hashes.pop(item_id)
        members = self._exact[hashes.sha256]
        members.remove(item_id)
        if not members:
            del self._exact[hashes.sha256]

    def find(self, hashes: ImageHashes) -> list[DuplicateMatch]:
        matches: list[DuplicateMatch] = []
        exact_ids = self._exact.get(hashes.sha256, set())
        for item_id in sorted(exact_ids):
            matches.append(DuplicateMatch(item_id=item_id, kind="exact", distance=0))
        for item_id, candidate in sorted(self._hashes.items()):
            if item_id in exact_ids:
                continue
            distance = hamming_distance(hashes.phash, candidate.phash)
            if distance <= self.perceptual_threshold:
                matches.append(
                    DuplicateMatch(item_id=item_id, kind="perceptual", distance=distance)
                )
        return sorted(
            matches, key=lambda match: (match.distance, match.kind != "exact", match.item_id)
        )
