from __future__ import annotations

import numpy as np
import pytest

from romanpics_worker.clustering import ClusterSnapshot, StableClusterReconciler
from romanpics_worker.similarity import SimilarityItem, group_similar_items


def item(
    item_id: str,
    content_class: str,
    embedding: list[float],
    families: set[str] | None = None,
) -> SimilarityItem:
    return SimilarityItem(
        item_id=item_id,
        content_class=content_class,
        embedding=np.asarray(embedding, dtype=np.float32),
        family_keys=frozenset(families or ()),
    )


def test_content_classes_never_mix_even_with_identical_vectors() -> None:
    result = group_similar_items(
        [
            item("science-a", "flight-science", [1, 0]),
            item("science-b", "flight-science", [0.99, 0.01]),
            item("hardware", "hardware-photo", [1, 0]),
        ],
        cosine_threshold=0.9,
    )
    assert {frozenset(group) for group in result.groups} == {
        frozenset({"science-a", "science-b"}),
        frozenset({"hardware"}),
    }


def test_same_observation_family_creates_deterministic_edge_despite_visual_distance() -> None:
    result = group_similar_items(
        [
            item("f087", "simulation", [1, 0], {"observation:demo-1"}),
            item("f184", "simulation", [-1, 0], {"observation:demo-1"}),
            item("other", "simulation", [0, 1]),
        ],
        cosine_threshold=0.99,
        neighbors=1,
    )
    assert frozenset({"f087", "f184"}) in result.groups
    family_edges = [edge for edge in result.edges if edge.reason.startswith("family:")]
    assert [(edge.left, edge.right) for edge in family_edges] == [("f087", "f184")]


def test_grouping_is_order_independent_and_validates_partition_input() -> None:
    items = [item("a", "science", [1, 0]), item("b", "science", [0.95, 0.05])]
    forward = group_similar_items(items)
    reverse = group_similar_items(list(reversed(items)))
    assert forward == reverse
    with pytest.raises(ValueError, match="unique"):
        group_similar_items([items[0], items[0]])


def initial_snapshot() -> ClusterSnapshot:
    reconciler = StableClusterReconciler(minimum_jaccard=0.15)
    return reconciler.reconcile(None, [{"a", "b", "c", "d"}, {"x", "y"}], run_id="run-1").snapshot


def cluster_for(snapshot: ClusterSnapshot, member: str):
    return next(cluster for cluster in snapshot.active if member in cluster.members)


def test_stable_identity_survives_update_and_old_version_is_archived() -> None:
    previous = initial_snapshot()
    prior = cluster_for(previous, "a")
    result = StableClusterReconciler().reconcile(
        previous, [{"a", "b", "c", "d", "e"}, {"x", "y"}], run_id="run-2"
    )
    current = cluster_for(result.snapshot, "a")
    assert current.cluster_id == prior.cluster_id
    assert current.version == prior.version + 1
    assert any(
        event.cluster_id == prior.cluster_id and event.reason == "superseded"
        for event in result.archived
    )
    unchanged = cluster_for(result.snapshot, "x")
    assert unchanged.version == cluster_for(previous, "x").version


def test_split_keeps_id_on_strongest_child_and_records_new_branch() -> None:
    previous = initial_snapshot()
    source = cluster_for(previous, "a")
    result = StableClusterReconciler(minimum_jaccard=0.15).reconcile(
        previous,
        [{"a", "b", "c"}, {"d", "new"}, {"x", "y"}],
        run_id="run-split",
    )
    primary = cluster_for(result.snapshot, "a")
    branch = cluster_for(result.snapshot, "d")
    assert primary.cluster_id == source.cluster_id
    assert branch.cluster_id != source.cluster_id
    assert source.cluster_id in branch.predecessors
    split = next(event for event in result.lineage if event.kind == "split")
    assert split.source_ids == (source.cluster_id,)
    assert set(split.target_ids) == {primary.cluster_id, branch.cluster_id}


def test_merge_keeps_one_id_and_archives_absorbed_identity() -> None:
    previous = initial_snapshot()
    old_ids = {cluster.cluster_id for cluster in previous.active}
    result = StableClusterReconciler(minimum_jaccard=0.15).reconcile(
        previous, [{"a", "b", "c", "d", "x", "y"}], run_id="run-merge"
    )
    assert len(result.snapshot.active) == 1
    survivor = result.snapshot.active[0]
    assert survivor.cluster_id in old_ids
    absorbed = old_ids - {survivor.cluster_id}
    assert any(
        event.cluster_id in absorbed
        and event.reason == "merged_into"
        and event.successor_ids == (survivor.cluster_id,)
        for event in result.archived
    )
    merge = next(event for event in result.lineage if event.kind == "merge")
    assert set(merge.source_ids) == old_ids


def test_disappeared_cluster_is_archived_and_snapshots_round_trip(tmp_path) -> None:
    previous = initial_snapshot()
    vanished = cluster_for(previous, "x")
    result = StableClusterReconciler().reconcile(previous, [{"a", "b", "c", "d"}], run_id="run-3")
    assert any(
        event.cluster_id == vanished.cluster_id and event.reason == "disappeared"
        for event in result.archived
    )
    path = tmp_path / "snapshot.json"
    result.snapshot.save(path)
    assert ClusterSnapshot.load(path) == result.snapshot
