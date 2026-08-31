"""MAST product normalization and prompt-product lifecycle contracts.

Prompt products are modeled as mutable upstream resources. RomanPics keeps immutable
local generations keyed by a logical product identity, so an overwrite at one MAST
URI cannot silently change an existing catalog record.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal

ReleaseKind = Literal["prompt", "final"]


def _first(row: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return default


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class MastProductRecord:
    logical_key: str
    asset_uri: str
    content_token: str
    release_kind: ReleaseKind
    metadata_fingerprint: str
    metadata: Mapping[str, Any]
    supersedes: tuple[str, ...] = ()

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> MastProductRecord:
        asset_uri = str(_first(row, "dataURI", "product_uri", "uri", default=""))
        if not asset_uri:
            raise ValueError("MAST product has no data URI")
        release = str(_first(row, "release_kind", "releaseKind", default="prompt")).lower()
        if release not in {"prompt", "final"}:
            raise ValueError(f"unsupported release kind {release!r}")
        logical_key = str(_first(row, "logical_key", "logicalKey", default=""))
        if not logical_key:
            parts = [
                str(_first(row, "obs_id", "obsid", default="unknown-observation")),
                str(_first(row, "detector", default="unknown-detector")),
                str(_first(row, "filter", "filters", default="unknown-filter")),
                str(
                    _first(
                        row, "productSubGroupDescription", "product_type", default="unknown-product"
                    )
                ),
            ]
            logical_key = ":".join(parts)
        content_token = str(_first(row, "checksum", "content_hash", "etag", default=""))
        if not content_token:
            content_token = _fingerprint(
                {
                    "uri": asset_uri,
                    "size": _first(row, "size", "size_bytes"),
                    "modified": _first(row, "lastModified", "updated_at"),
                }
            )
        supersedes_value = _first(row, "supersedes", default=())
        if isinstance(supersedes_value, str):
            supersedes = (supersedes_value,)
        else:
            supersedes = tuple(sorted(str(value) for value in supersedes_value))
        metadata = dict(row)
        return cls(
            logical_key=logical_key,
            asset_uri=asset_uri,
            content_token=content_token,
            release_kind=release,  # type: ignore[arg-type]
            metadata_fingerprint=_fingerprint(metadata),
            metadata=metadata,
            supersedes=supersedes,
        )


@dataclass(frozen=True)
class ProductGeneration:
    logical_key: str
    generation: int
    asset_uri: str
    content_token: str
    release_kind: ReleaseKind
    metadata_fingerprint: str
    status: Literal["active", "replaced", "superseded"]
    first_seen_run: str
    last_seen_run: str
    superseded_by: str | None = None


@dataclass(frozen=True)
class ProductEvent:
    kind: Literal["created", "unchanged", "metadata_updated", "overwritten", "superseded"]
    logical_key: str
    generation: int
    prior_generation: int | None = None


class MastProductRegistry:
    """An in-memory reference implementation of immutable product generations."""

    def __init__(self):
        self._history: dict[str, list[ProductGeneration]] = {}

    def history(self, logical_key: str) -> tuple[ProductGeneration, ...]:
        return tuple(self._history.get(logical_key, ()))

    def active(self) -> tuple[ProductGeneration, ...]:
        return tuple(
            sorted(
                (
                    generation
                    for history in self._history.values()
                    for generation in history
                    if generation.status == "active"
                ),
                key=lambda generation: generation.logical_key,
            )
        )

    def apply_rows(
        self, rows: Sequence[Mapping[str, Any]], *, run_id: str
    ) -> tuple[ProductEvent, ...]:
        if not run_id:
            raise ValueError("run_id is required")
        records = sorted(
            (MastProductRecord.from_row(row) for row in rows),
            key=lambda record: (record.logical_key, record.release_kind, record.asset_uri),
        )
        events: list[ProductEvent] = []
        for record in records:
            history = self._history.setdefault(record.logical_key, [])
            current_index = next(
                (
                    index
                    for index in range(len(history) - 1, -1, -1)
                    if history[index].status == "active"
                ),
                None,
            )
            current = history[current_index] if current_index is not None else None
            if current is None:
                generation = ProductGeneration(
                    logical_key=record.logical_key,
                    generation=1,
                    asset_uri=record.asset_uri,
                    content_token=record.content_token,
                    release_kind=record.release_kind,
                    metadata_fingerprint=record.metadata_fingerprint,
                    status="active",
                    first_seen_run=run_id,
                    last_seen_run=run_id,
                )
                history.append(generation)
                events.append(ProductEvent("created", record.logical_key, generation.generation))
                self._apply_explicit_supersession(record, generation, run_id, events)
                continue

            same_content = (
                current.asset_uri == record.asset_uri
                and current.content_token == record.content_token
            )
            if same_content:
                kind = (
                    "unchanged"
                    if current.metadata_fingerprint == record.metadata_fingerprint
                    else "metadata_updated"
                )
                history[current_index] = replace(
                    current,
                    metadata_fingerprint=record.metadata_fingerprint,
                    last_seen_run=run_id,
                )
                events.append(ProductEvent(kind, record.logical_key, current.generation))
                continue

            supersession = (
                record.release_kind == "final"
                and current.release_kind == "prompt"
                or current.asset_uri in record.supersedes
                or current.logical_key in record.supersedes
            )
            archived_status = "superseded" if supersession else "replaced"
            generation_number = current.generation + 1
            history[current_index] = replace(
                current,
                status=archived_status,
                last_seen_run=run_id,
                superseded_by=record.asset_uri,
            )
            generation = ProductGeneration(
                logical_key=record.logical_key,
                generation=generation_number,
                asset_uri=record.asset_uri,
                content_token=record.content_token,
                release_kind=record.release_kind,
                metadata_fingerprint=record.metadata_fingerprint,
                status="active",
                first_seen_run=run_id,
                last_seen_run=run_id,
            )
            history.append(generation)
            kind = "superseded" if supersession else "overwritten"
            events.append(
                ProductEvent(kind, record.logical_key, generation_number, current.generation)
            )
            self._apply_explicit_supersession(record, generation, run_id, events)
        return tuple(events)

    def _apply_explicit_supersession(
        self,
        record: MastProductRecord,
        successor: ProductGeneration,
        run_id: str,
        events: list[ProductEvent],
    ) -> None:
        if not record.supersedes:
            return
        for logical_key, history in sorted(self._history.items()):
            if logical_key == record.logical_key:
                continue
            for index, generation in enumerate(history):
                if generation.status != "active":
                    continue
                if generation.asset_uri in record.supersedes or logical_key in record.supersedes:
                    history[index] = replace(
                        generation,
                        status="superseded",
                        last_seen_run=run_id,
                        superseded_by=successor.asset_uri,
                    )
                    events.append(
                        ProductEvent(
                            "superseded", logical_key, successor.generation, generation.generation
                        )
                    )


def extract_mast_rows(response: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Validate the minimal MAST response envelope used by recorded fixtures."""

    status = response.get("status")
    if status not in (None, "COMPLETE"):
        raise ValueError(f"MAST response is not complete: {status!r}")
    rows = response.get("data")
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise ValueError("MAST response data must be a list of records")
    return rows
