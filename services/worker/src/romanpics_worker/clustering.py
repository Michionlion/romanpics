"""Stable, versioned identities over changing similarity clusters."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class ClusterVersion:
    cluster_id: str
    version: int
    members: frozenset[str]
    created_run: str
    updated_run: str
    predecessors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["members"] = sorted(self.members)
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ClusterVersion:
        return cls(
            cluster_id=value["cluster_id"],
            version=int(value["version"]),
            members=frozenset(value["members"]),
            created_run=value["created_run"],
            updated_run=value["updated_run"],
            predecessors=tuple(value.get("predecessors", ())),
        )


ArchiveReason = Literal["superseded", "merged_into", "split_into", "disappeared"]


@dataclass(frozen=True)
class ArchiveEvent:
    cluster_id: str
    version: int
    reason: ArchiveReason
    successor_ids: tuple[str, ...]
    archived_run: str


@dataclass(frozen=True)
class LineageEvent:
    kind: Literal["created", "updated", "unchanged", "split", "merge", "disappeared"]
    source_ids: tuple[str, ...]
    target_ids: tuple[str, ...]


@dataclass(frozen=True)
class ClusterSnapshot:
    run_id: str
    active: tuple[ClusterVersion, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "active": [cluster.to_dict() for cluster in self.active]}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ClusterSnapshot:
        return cls(
            run_id=value["run_id"],
            active=tuple(ClusterVersion.from_dict(item) for item in value.get("active", ())),
        )

    @classmethod
    def load(cls, path: str | Path) -> ClusterSnapshot:
        return cls.from_dict(json.loads(Path(path).read_text()))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")


@dataclass(frozen=True)
class ReconciliationResult:
    snapshot: ClusterSnapshot
    archived: tuple[ArchiveEvent, ...]
    lineage: tuple[LineageEvent, ...]


def _fingerprint(members: frozenset[str]) -> str:
    return hashlib.sha256("\0".join(sorted(members)).encode()).hexdigest()


def _new_cluster_id(members: frozenset[str], run_id: str, occupied: set[str]) -> str:
    attempt = 0
    while True:
        material = f"{run_id}\0{_fingerprint(members)}\0{attempt}".encode()
        candidate = f"grp_{hashlib.sha256(material).hexdigest()[:16]}"
        if candidate not in occupied:
            occupied.add(candidate)
            return candidate
        attempt += 1


class StableClusterReconciler:
    """Carry stable IDs forward with deterministic maximum-overlap matching.

    The strongest one-to-one overlaps inherit identities. Additional children of an
    old cluster are marked as splits; additional parents of a new cluster are archived
    as merges. Old immutable versions are archived whenever membership changes.
    """

    def __init__(self, *, minimum_jaccard: float = 0.15):
        if not 0 <= minimum_jaccard <= 1:
            raise ValueError("minimum_jaccard must be between zero and one")
        self.minimum_jaccard = minimum_jaccard

    def reconcile(
        self,
        previous: ClusterSnapshot | None,
        new_groups: Sequence[Sequence[str] | set[str] | frozenset[str]],
        *,
        run_id: str,
    ) -> ReconciliationResult:
        if not run_id:
            raise ValueError("run_id is required")
        groups = [frozenset(str(member) for member in group) for group in new_groups]
        if any(not group for group in groups):
            raise ValueError("clusters may not be empty")
        all_members = [member for group in groups for member in group]
        if len(all_members) != len(set(all_members)):
            raise ValueError("an item may appear in only one output cluster")
        groups.sort(key=lambda group: (_fingerprint(group), sorted(group)))

        old = sorted(previous.active if previous else (), key=lambda cluster: cluster.cluster_id)
        occupied = {cluster.cluster_id for cluster in old}

        # Candidate tuple: overlap, jaccard, old containment, new containment, old index, new index.
        candidates: list[tuple[int, float, float, float, int, int]] = []
        eligible_by_old: dict[int, set[int]] = {index: set() for index in range(len(old))}
        eligible_by_new: dict[int, set[int]] = {index: set() for index in range(len(groups))}
        for old_index, prior in enumerate(old):
            for new_index, group in enumerate(groups):
                overlap = len(prior.members & group)
                if overlap == 0:
                    continue
                union = len(prior.members | group)
                jaccard = overlap / union
                if jaccard < self.minimum_jaccard:
                    continue
                old_fraction = overlap / len(prior.members)
                new_fraction = overlap / len(group)
                candidates.append(
                    (overlap, jaccard, old_fraction, new_fraction, old_index, new_index)
                )
                eligible_by_old[old_index].add(new_index)
                eligible_by_new[new_index].add(old_index)

        # Deterministic greedy maximum-overlap matching. The stable ID breaks exact ties.
        candidates.sort(
            key=lambda item: (
                -item[0],
                -item[1],
                -item[2],
                -item[3],
                old[item[4]].cluster_id,
                _fingerprint(groups[item[5]]),
            )
        )
        old_to_new: dict[int, int] = {}
        new_to_old: dict[int, int] = {}
        for _overlap, _jaccard, _old_fraction, _new_fraction, old_index, new_index in candidates:
            if old_index not in old_to_new and new_index not in new_to_old:
                old_to_new[old_index] = new_index
                new_to_old[new_index] = old_index

        current: list[ClusterVersion] = []
        ids_by_new: dict[int, str] = {}
        archived: list[ArchiveEvent] = []
        lineage: list[LineageEvent] = []

        for new_index, members in enumerate(groups):
            sources = tuple(sorted(old[index].cluster_id for index in eligible_by_new[new_index]))
            if new_index in new_to_old:
                prior = old[new_to_old[new_index]]
                cluster_id = prior.cluster_id
                changed = prior.members != members
                version = prior.version + 1 if changed else prior.version
                cluster = ClusterVersion(
                    cluster_id=cluster_id,
                    version=version,
                    members=members,
                    created_run=prior.created_run,
                    updated_run=run_id if changed else prior.updated_run,
                    predecessors=sources,
                )
                if changed:
                    archived.append(
                        ArchiveEvent(
                            cluster_id=prior.cluster_id,
                            version=prior.version,
                            reason="superseded",
                            successor_ids=(prior.cluster_id,),
                            archived_run=run_id,
                        )
                    )
                    lineage.append(
                        LineageEvent("updated", (prior.cluster_id,), (prior.cluster_id,))
                    )
                else:
                    lineage.append(
                        LineageEvent("unchanged", (prior.cluster_id,), (prior.cluster_id,))
                    )
            else:
                cluster_id = _new_cluster_id(members, run_id, occupied)
                cluster = ClusterVersion(
                    cluster_id=cluster_id,
                    version=1,
                    members=members,
                    created_run=run_id,
                    updated_run=run_id,
                    predecessors=sources,
                )
                if not sources:
                    lineage.append(LineageEvent("created", (), (cluster_id,)))
            ids_by_new[new_index] = cluster_id
            current.append(cluster)

        # Describe whole split/merge topology after every target ID is known.
        for old_index, targets in sorted(eligible_by_old.items()):
            if len(targets) > 1:
                lineage.append(
                    LineageEvent(
                        "split",
                        (old[old_index].cluster_id,),
                        tuple(sorted(ids_by_new[index] for index in targets)),
                    )
                )
        for new_index, sources in sorted(eligible_by_new.items()):
            if len(sources) > 1:
                lineage.append(
                    LineageEvent(
                        "merge",
                        tuple(sorted(old[index].cluster_id for index in sources)),
                        (ids_by_new[new_index],),
                    )
                )

        for old_index, prior in enumerate(old):
            if old_index in old_to_new:
                continue
            targets = tuple(sorted(ids_by_new[index] for index in eligible_by_old[old_index]))
            if not targets:
                reason: ArchiveReason = "disappeared"
                lineage.append(LineageEvent("disappeared", (prior.cluster_id,), ()))
            elif len(targets) > 1:
                reason = "split_into"
            else:
                reason = "merged_into"
            archived.append(
                ArchiveEvent(
                    cluster_id=prior.cluster_id,
                    version=prior.version,
                    reason=reason,
                    successor_ids=targets,
                    archived_run=run_id,
                )
            )

        snapshot = ClusterSnapshot(
            run_id=run_id,
            active=tuple(sorted(current, key=lambda cluster: cluster.cluster_id)),
        )
        return ReconciliationResult(
            snapshot=snapshot,
            archived=tuple(
                sorted(archived, key=lambda event: (event.cluster_id, event.version, event.reason))
            ),
            lineage=tuple(
                sorted(lineage, key=lambda event: (event.kind, event.source_ids, event.target_ids))
            ),
        )
