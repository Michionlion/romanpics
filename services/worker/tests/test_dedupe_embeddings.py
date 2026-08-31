from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageEnhance

from romanpics_worker.dedupe import (
    DuplicateIndex,
    ImageHashes,
    hamming_distance,
    hashes_for_bytes,
    perceptual_hash,
)
from romanpics_worker.embeddings import (
    CombinedEmbedder,
    DeterministicMetadataEmbedder,
    DeterministicVisualEmbedder,
)


def png_bytes(array: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(array.astype(np.uint8), mode="RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def test_exact_and_perceptual_hashes() -> None:
    y, x = np.mgrid[:64, :64]
    array = np.stack((x * 4, y * 4, ((x + y) % 64) * 4), axis=-1)
    payload = png_bytes(array)
    same = hashes_for_bytes(payload)
    assert same == hashes_for_bytes(payload)
    with Image.open(io.BytesIO(payload)) as image:
        brighter = ImageEnhance.Brightness(image).enhance(0.9)
        bright_hash = perceptual_hash(brighter)
    assert hamming_distance(same.phash, bright_hash) <= 16


def test_duplicate_index_prefers_exact_then_near_matches() -> None:
    index = DuplicateIndex(perceptual_threshold=2)
    index.add("exact", ImageHashes("a" * 64, "0000000000000000"))
    index.add("near", ImageHashes("b" * 64, "0000000000000003"))
    index.add("far", ImageHashes("c" * 64, "ffffffffffffffff"))
    matches = index.find(ImageHashes("a" * 64, "0000000000000001"))
    assert [(match.item_id, match.kind, match.distance) for match in matches] == [
        ("exact", "exact", 0),
        ("near", "perceptual", 1),
    ]


def test_lightweight_embeddings_are_deterministic_normalized_and_order_independent() -> None:
    image = np.zeros((40, 50, 3), dtype=np.uint8)
    image[5:20, 10:30] = (220, 40, 80)
    visual = DeterministicVisualEmbedder(dimension=64)
    first = visual.embed(image)
    second = visual.embed(image.copy())
    assert np.array_equal(first, second)
    assert np.isclose(np.linalg.norm(first), 1.0)

    metadata = DeterministicMetadataEmbedder(dimension=64)
    left = metadata.embed({"target": "Andromeda", "filters": ["F158", "F087"]})
    right = metadata.embed({"filters": ["F087", "F158"], "target": "Andromeda"})
    assert np.array_equal(left, right)
    assert np.isclose(np.linalg.norm(left), 1.0)

    combined = CombinedEmbedder(visual, metadata).embed(image, {"target": "Andromeda"})
    assert combined.shape == (128,)
    assert np.isclose(np.linalg.norm(combined), 1.0)
