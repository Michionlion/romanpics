"""Deterministic similarity grouping before stable-ID reconciliation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

SIMILARITY_ALGORITHM_VERSION = "cosine-knn-components-v1"


@dataclass(frozen=True)
class SimilarityItem:
    item_id: str
    content_class: str
    embedding: np.ndarray = field(compare=False, repr=False)
    # Examples: ``observation:ROMAN-...``, ``asset-family:...``, or an upstream
    # collection/product family. Equal keys create explicit, auditable edges.
    family_keys: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class SimilarityEdge:
    left: str
    right: str
    reason: str
    cosine: float | None = None


@dataclass(frozen=True)
class GroupingResult:
    groups: tuple[frozenset[str], ...]
    edges: tuple[SimilarityEdge, ...]
    algorithm_version: str = SIMILARITY_ALGORITHM_VERSION


class _DisjointSet:
    def __init__(self, values: Sequence[str]):
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        root = value
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[value] != value:
            next_value = self.parent[value]
            self.parent[value] = root
            value = next_value
        return root

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        # Lexical roots make component output independent of traversal order.
        first, second = sorted((left_root, right_root))
        self.parent[second] = first


def group_similar_items(
    items: Sequence[SimilarityItem],
    *,
    cosine_threshold: float = 0.86,
    neighbors: int = 8,
) -> GroupingResult:
    """Build per-class cosine k-NN graphs and return connected components.

    Content classes are hard partitions: a simulation can never be pulled into a
    hardware photo cluster merely because their embeddings are close. Explicit
    family keys add deterministic edges inside a class even when visual similarity
    is weak, keeping products from one observation/family together.
    """

    if not -1 <= cosine_threshold <= 1:
        raise ValueError("cosine_threshold must be between -1 and 1")
    if neighbors < 0:
        raise ValueError("neighbors must be non-negative")
    ordered = sorted(items, key=lambda item: item.item_id)
    identifiers = [item.item_id for item in ordered]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("item IDs must be unique")
    if not ordered:
        return GroupingResult(groups=(), edges=())

    dimensions = {np.asarray(item.embedding).size for item in ordered}
    if len(dimensions) != 1 or next(iter(dimensions)) == 0:
        raise ValueError("all embeddings must have one common non-zero dimension")
    vectors: dict[str, np.ndarray] = {}
    for item in ordered:
        vector = np.asarray(item.embedding, dtype=np.float64).reshape(-1)
        if not np.all(np.isfinite(vector)):
            raise ValueError(f"embedding for {item.item_id!r} contains non-finite values")
        norm = float(np.linalg.norm(vector))
        vectors[item.item_id] = vector / norm if norm else vector

    disjoint = _DisjointSet(identifiers)
    edge_map: dict[tuple[str, str], SimilarityEdge] = {}
    classes = sorted({item.content_class for item in ordered})
    for content_class in classes:
        partition = [item for item in ordered if item.content_class == content_class]

        # Exact family edges are independent from learned embedding versions.
        families: dict[str, list[str]] = {}
        for item in partition:
            for key in sorted(item.family_keys):
                if key:
                    families.setdefault(key, []).append(item.item_id)
        for key, members in sorted(families.items()):
            for left, right in zip(sorted(members), sorted(members)[1:], strict=False):
                pair = (left, right)
                edge_map[pair] = SimilarityEdge(left, right, reason=f"family:{key}")
                disjoint.union(left, right)

        if neighbors == 0:
            continue
        for item in partition:
            candidates: list[tuple[float, str]] = []
            for candidate in partition:
                if candidate.item_id == item.item_id:
                    continue
                cosine = float(vectors[item.item_id] @ vectors[candidate.item_id])
                if cosine >= cosine_threshold:
                    candidates.append((cosine, candidate.item_id))
            candidates.sort(key=lambda pair: (-pair[0], pair[1]))
            for cosine, candidate_id in candidates[:neighbors]:
                left, right = sorted((item.item_id, candidate_id))
                pair = (left, right)
                # Family provenance takes precedence, though cosine is reproducible too.
                edge_map.setdefault(
                    pair, SimilarityEdge(left, right, reason="cosine", cosine=cosine)
                )
                disjoint.union(left, right)

    components: dict[str, set[str]] = {}
    for identifier in identifiers:
        components.setdefault(disjoint.find(identifier), set()).add(identifier)
    groups = tuple(
        sorted(
            (frozenset(members) for members in components.values()),
            key=lambda members: tuple(sorted(members)),
        )
    )
    edges = tuple(sorted(edge_map.values(), key=lambda edge: (edge.left, edge.right, edge.reason)))
    return GroupingResult(groups=groups, edges=edges)
