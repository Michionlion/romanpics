"""Resolve trusted job IDs into worker inputs from the canonical catalog.

URLs never come from queue payloads. A resolver verifies relationships and checksums
in the backend database, then the separately configured source policy validates the
resolved URL before any network request.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from .clustering import (
    ArchiveEvent,
    ClusterSnapshot,
    ClusterVersion,
    LineageEvent,
    StableClusterReconciler,
)
from .contracts import ClusterPayload, EmbedPayload, LinkCheckPayload, RenderPayload
from .similarity import SimilarityItem


@dataclass(frozen=True)
class ResolvedRenderInput:
    source_url: str
    media_type: str
    source_record_id: str = ""
    source_checksum: str = ""
    alt_text: str = "Roman Space Telescope observation"
    credit: str = "NASA Roman Space Telescope"
    rights: str | None = None
    rights_url: str | None = None


@dataclass(frozen=True)
class ResolvedEmbedInput:
    image_url: str
    metadata: Mapping[str, Any]
    site_generated: bool = False


@dataclass(frozen=True)
class ResolvedClusterInput:
    items: tuple[SimilarityItem, ...]
    eligible_item_count: int | None = None


@dataclass(frozen=True)
class LinkTarget:
    url: str
    target_kind: str
    target_id: str
    site_generated: bool = False


class JobInputResolver(Protocol):
    def resolve_render(self, payload: RenderPayload) -> ResolvedRenderInput: ...

    def resolve_embed(self, payload: EmbedPayload) -> ResolvedEmbedInput: ...

    def resolve_cluster(self, payload: ClusterPayload) -> ResolvedClusterInput: ...

    def resolve_link_targets(self, payload: LinkCheckPayload) -> Sequence[LinkTarget]: ...


class JobResultSink(Protocol):
    def persist_render(
        self, payload: RenderPayload, result: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    def persist_embedding(
        self, payload: EmbedPayload, result: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    def persist_clusters(
        self, payload: ClusterPayload, result: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    def persist_link_checks(
        self, payload: LinkCheckPayload, result: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...


ROMANPICS_NAMESPACE = uuid.UUID("65b45bda-080e-53bb-a019-17641a1939ac")
RENDER_PENDING_NOTE = "Awaiting a bounded site-generated preview."


def _stable_uuid(kind: str, key: str) -> str:
    return str(uuid.uuid5(ROMANPICS_NAMESPACE, f"{kind}:{key}"))


def _json_object(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str | bytes):
        value = json.loads(value)
    if not isinstance(value, Mapping):
        raise RuntimeError("catalog metadata is not a JSON object")
    return dict(value)


def _json_vector(value: Any) -> np.ndarray:
    if isinstance(value, str | bytes):
        value = json.loads(value)
    vector = np.asarray(value, dtype=np.float32).reshape(-1)
    if not vector.size or not np.all(np.isfinite(vector)):
        raise RuntimeError("catalog embedding is empty or non-finite")
    return vector


def _public_previews(result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = result.get("previews")
    if not isinstance(value, list) or not value:
        raise RuntimeError("render produced no previews")
    previews: list[Mapping[str, Any]] = []
    for preview in value:
        if not isinstance(preview, Mapping):
            raise RuntimeError("render preview result is malformed")
        public_url = preview.get("public_url")
        if not isinstance(public_url, str) or not public_url.startswith("https://"):
            raise RuntimeError("render cannot publish without an HTTPS preview public_url")
        if not isinstance(preview.get("width"), int) or not isinstance(preview.get("height"), int):
            raise RuntimeError("render preview dimensions are malformed")
        previews.append(preview)
    return previews


def _embedding_result(result: Mapping[str, Any]) -> tuple[str, str, list[float], str | None]:
    model = result.get("model")
    version = result.get("version")
    vector_value = result.get("vector")
    perceptual_hash = result.get("perceptual_hash")
    if not isinstance(model, str) or not model or not isinstance(version, str) or not version:
        raise RuntimeError("embedding model/version are missing")
    vector = _json_vector(vector_value).astype(float).tolist()
    if perceptual_hash is not None and not isinstance(perceptual_hash, str):
        raise RuntimeError("embedding perceptual hash is malformed")
    return model, version, vector, perceptual_hash


def _cluster_inputs(
    result: Mapping[str, Any],
) -> tuple[str, tuple[frozenset[str], ...], tuple[dict[str, Any], ...]]:
    algorithm_version = result.get("algorithm_version")
    groups_value = result.get("groups")
    edges_value = result.get("edges")
    if not isinstance(algorithm_version, str) or not algorithm_version:
        raise RuntimeError("cluster result has no algorithm version")
    if not isinstance(groups_value, list) or not isinstance(edges_value, list):
        raise RuntimeError("cluster result groups/edges are malformed")
    groups: list[frozenset[str]] = []
    for value in groups_value:
        if (
            not isinstance(value, list)
            or not value
            or not all(isinstance(item, str) for item in value)
        ):
            raise RuntimeError("cluster result contains a malformed group")
        groups.append(frozenset(value))
    edges: list[dict[str, Any]] = []
    for value in edges_value:
        if not isinstance(value, Mapping):
            raise RuntimeError("cluster result contains a malformed edge")
        left, right, reason, cosine = (
            value.get("left"),
            value.get("right"),
            value.get("reason"),
            value.get("cosine"),
        )
        if (
            not isinstance(left, str)
            or not isinstance(right, str)
            or left == right
            or not isinstance(reason, str)
            or not reason
            or (cosine is not None and not isinstance(cosine, int | float))
        ):
            raise RuntimeError("cluster result contains a malformed edge")
        score = float(cosine) if cosine is not None else 1.0
        if not np.isfinite(score) or not -1.0 <= score <= 1.0:
            raise RuntimeError("cluster result contains an invalid similarity score")
        first, second = sorted((left, right))
        edges.append({"left": first, "right": second, "reason": reason, "score": score})
    return algorithm_version, tuple(groups), tuple(edges)


def _previous_snapshot(rows: Sequence[Mapping[str, Any]]) -> ClusterSnapshot | None:
    members: dict[str, set[str]] = {}
    created: dict[str, str] = {}
    updated: dict[str, str] = {}
    for row in rows:
        cluster_id = str(row["cluster_id"])
        members.setdefault(cluster_id, set()).add(str(row["item_id"]))
        created.setdefault(cluster_id, str(row["created_at"] or "catalog"))
        updated[cluster_id] = str(row["updated_at"] or created[cluster_id])
    if not members:
        return None
    return ClusterSnapshot(
        run_id="catalog",
        active=tuple(
            ClusterVersion(
                cluster_id=cluster_id,
                version=1,
                members=frozenset(item_ids),
                created_run=created[cluster_id],
                updated_run=updated[cluster_id],
            )
            for cluster_id, item_ids in sorted(members.items())
        ),
    )


def _mapped_reconciliation(
    snapshot: ClusterSnapshot,
    archived: Sequence[ArchiveEvent],
    lineage: Sequence[LineageEvent],
    identifiers: Mapping[str, str],
) -> dict[str, Any]:
    def mapped(identifier: str) -> str:
        return identifiers.get(identifier, identifier)

    return {
        "snapshot": {
            "run_id": snapshot.run_id,
            "active": [
                {
                    **cluster.to_dict(),
                    "cluster_id": mapped(cluster.cluster_id),
                    "predecessors": [mapped(value) for value in cluster.predecessors],
                }
                for cluster in snapshot.active
            ],
        },
        "archived": [
            {
                **asdict(event),
                "cluster_id": mapped(event.cluster_id),
                "successor_ids": [mapped(value) for value in event.successor_ids],
            }
            for event in archived
        ],
        "lineage": [
            {
                **asdict(event),
                "source_ids": [mapped(value) for value in event.source_ids],
                "target_ids": [mapped(value) for value in event.target_ids],
            }
            for event in lineage
        ],
    }


def _member_score(
    item_id: str,
    representative: str,
    members: frozenset[str],
    score_by_pair: Mapping[tuple[str, str], float],
) -> float:
    if item_id == representative:
        return 1.0
    return max(
        (
            score
            for pair, score in score_by_pair.items()
            if item_id in pair and pair[0] in members and pair[1] in members
        ),
        default=0.0,
    )


def _checks(result: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    job_id = result.get("job_id")
    values = result.get("checks")
    if not isinstance(job_id, str) or not job_id or not isinstance(values, list):
        raise RuntimeError("link-check result is malformed")
    checks: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise RuntimeError("link-check result contains a malformed target")
        url = value.get("url")
        target_kind = value.get("target_kind")
        target_id = value.get("target_id")
        ok = value.get("ok")
        status_code = value.get("status_code")
        final_url = value.get("final_url")
        error = value.get("error")
        if (
            not isinstance(url, str)
            or not isinstance(target_kind, str)
            or not isinstance(target_id, str)
            or not isinstance(ok, bool)
            or (status_code is not None and not isinstance(status_code, int))
            or (final_url is not None and not isinstance(final_url, str))
            or (error is not None and not isinstance(error, str))
        ):
            raise RuntimeError("link-check result contains a malformed target")
        checks.append(
            {
                "url": url,
                "target_kind": target_kind,
                "target_id": target_id,
                "ok": ok,
                "status_code": status_code,
                "final_url": final_url,
                "error": error[:2000] if error else None,
            }
        )
    return job_id, checks


class _CatalogResolver:
    placeholder = "%s"

    def _rows(self, query: str, parameters: tuple[Any, ...]) -> list[Mapping[str, Any]]:
        raise NotImplementedError

    def _one(self, query: str, parameters: tuple[Any, ...]) -> Mapping[str, Any] | None:
        rows = self._rows(query, parameters)
        return rows[0] if rows else None

    def resolve_render(self, payload: RenderPayload) -> ResolvedRenderInput:
        row = self._one(
            f"""
            SELECT product.external_url, product.media_type,
                   record.id AS source_record_id, record.checksum,
                   record.raw_metadata, item.metadata_json, item.alt_text
            FROM archive_product AS product
            JOIN item_asset AS asset ON asset.product_id = product.id
            JOIN source_record AS record ON record.id = product.source_record_id
            JOIN gallery_item AS item ON item.id = asset.item_id
                                      AND item.primary_source_record_id = record.id
            WHERE asset.item_id = {self.placeholder}
              AND product.id = {self.placeholder}
              AND product.active
            LIMIT 1
            """,
            (payload["item_id"], payload["product_id"]),
        )
        if row is None:
            raise LookupError("render product is missing, inactive, or not attached to the item")
        raw = _json_object(row["raw_metadata"])
        metadata = _json_object(row["metadata_json"])
        credit = str(raw.get("credit") or metadata.get("credit") or "NASA Roman Space Telescope")
        rights_value = raw.get("rights") or metadata.get("rights")
        rights_url_value = raw.get("rights_url") or metadata.get("rights_url")
        return ResolvedRenderInput(
            source_url=str(row["external_url"]),
            media_type=str(row["media_type"]),
            source_record_id=str(row["source_record_id"]),
            source_checksum=str(row["checksum"]),
            alt_text=str(row["alt_text"]),
            credit=credit,
            rights=str(rights_value) if rights_value else None,
            rights_url=str(rights_url_value) if rights_url_value else None,
        )

    def resolve_embed(self, payload: EmbedPayload) -> ResolvedEmbedInput:
        item = self._one(
            f"""
            SELECT item.id, item.title, item.plain_summary, item.content_class,
                   item.metadata_json, item.primary_observation_id, record.checksum
            FROM gallery_item AS item
            JOIN source_record AS record ON record.id = item.primary_source_record_id
            WHERE item.id = {self.placeholder}
              AND record.id = {self.placeholder}
              AND record.checksum = {self.placeholder}
              AND record.state = 'active'
            LIMIT 1
            """,
            (payload["item_id"], payload["source_record_id"], payload["checksum"]),
        )
        if item is None:
            raise LookupError("embed item/source/checksum no longer identify an active record")
        rendition = self._one(
            f"""
            SELECT url, format, role, is_site_derivative
            FROM rendition
            WHERE item_id = {self.placeholder}
            ORDER BY CASE WHEN role = 'preview' THEN 0 ELSE 1 END,
                     is_site_derivative DESC, width DESC, created_at DESC
            LIMIT 1
            """,
            (payload["item_id"],),
        )
        if rendition is None:
            raise LookupError("embed item has no browser rendition")
        metadata = _json_object(item["metadata_json"])
        metadata.update(
            {
                "title": item["title"],
                "summary": item["plain_summary"],
                "content_class": item["content_class"],
                "observation_id": item["primary_observation_id"],
            }
        )
        return ResolvedEmbedInput(
            image_url=str(rendition["url"]),
            metadata=metadata,
            site_generated=bool(rendition["is_site_derivative"]),
        )

    def resolve_cluster(self, payload: ClusterPayload) -> ResolvedClusterInput:
        run = self._one(
            f"""SELECT id FROM ingest_run
                WHERE id = {self.placeholder} AND source_id = {self.placeholder}
                LIMIT 1""",
            (payload["ingest_run_id"], payload["source_id"]),
        )
        if run is None:
            raise LookupError("cluster ingest run does not belong to the requested source")
        eligible = self._one(
            """
            SELECT count(*) AS item_count
            FROM gallery_item AS item
            JOIN source_record AS record ON record.id = item.primary_source_record_id
            WHERE record.state = 'active' AND item.editorial_state = 'published'
            """,
            (),
        )
        rows = self._rows(
            """
            SELECT item.id AS item_id, item.content_class,
                   item.primary_observation_id, embedding.vector, embedding.updated_at
            FROM source_record AS record
            JOIN gallery_item AS item ON item.primary_source_record_id = record.id
            JOIN embedding ON embedding.item_id = item.id
            WHERE record.state = 'active'
              AND item.editorial_state = 'published'
              AND embedding.vector IS NOT NULL
            ORDER BY item.id ASC, embedding.updated_at DESC
            """,
            (),
        )
        latest: dict[str, SimilarityItem] = {}
        for row in rows:
            item_id = str(row["item_id"])
            if item_id in latest:
                continue
            observation_id = row["primary_observation_id"]
            families = (
                frozenset({f"observation:{observation_id}"})
                if observation_id is not None
                else frozenset()
            )
            latest[item_id] = SimilarityItem(
                item_id=item_id,
                content_class=str(row["content_class"]),
                embedding=_json_vector(row["vector"]),
                family_keys=families,
            )
        return ResolvedClusterInput(
            items=tuple(latest.values()),
            eligible_item_count=int(eligible["item_count"]) if eligible is not None else 0,
        )

    def resolve_link_targets(self, payload: LinkCheckPayload) -> Sequence[LinkTarget]:
        if payload["scope"] != "catalog":
            raise ValueError("jobs-v1 currently supports only the catalog link-check scope")
        queries = (
            ("source_record", "source_record", "canonical_url", "0"),
            ("rendition", "rendition", "url", "is_site_derivative"),
            ("archive_product", "archive_product", "external_url", "0"),
        )
        targets: dict[tuple[str, str, str], LinkTarget] = {}
        for kind, table, column, site_generated in queries:
            for row in self._rows(
                f"SELECT id, {column} AS url, {site_generated} AS site_generated FROM {table}",
                (),
            ):
                url = str(row["url"])
                key = (url, kind, str(row["id"]))
                targets.setdefault(
                    key,
                    LinkTarget(
                        url=url,
                        target_kind=kind,
                        target_id=str(row["id"]),
                        site_generated=bool(row["site_generated"]),
                    ),
                )
        return tuple(targets[key] for key in sorted(targets))


class SqliteCatalogResolver(_CatalogResolver):
    placeholder = "?"

    def __init__(self, database: str | Path):
        self.database = str(database)

    def _rows(self, query: str, parameters: tuple[Any, ...]) -> list[Mapping[str, Any]]:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        try:
            return list(connection.execute(query, parameters).fetchall())
        finally:
            connection.close()

    def persist_render(
        self, payload: RenderPayload, result: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        previews = _public_previews(result)
        now = datetime.now(UTC).isoformat()
        connection = sqlite3.connect(self.database, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN IMMEDIATE")
        try:
            item = connection.execute(
                """
                SELECT item.editorial_state, item.metadata_json, item.processing_note,
                       item.alt_text, record.id AS source_record_id, record.checksum
                FROM gallery_item AS item
                JOIN source_record AS record ON record.id = item.primary_source_record_id
                JOIN item_asset AS asset ON asset.item_id = item.id
                WHERE item.id = ? AND asset.product_id = ? AND record.state = 'active'
                LIMIT 1
                """,
                (payload["item_id"], payload["product_id"]),
            ).fetchone()
            if item is None:
                raise LookupError("render result no longer matches an active catalog item/product")
            recipe_json = json.dumps(payload["recipe"], sort_keys=True, separators=(",", ":"))
            for preview in previews:
                url = str(preview["public_url"])
                rendition_id = _stable_uuid("rendition", f"{payload['item_id']}:{url}")
                connection.execute(
                    """
                    INSERT INTO rendition (
                        id, item_id, provider, url, width, height, format,
                        is_site_derivative, recipe, alt_text, credit, rights,
                        rights_url, role, last_verified_at, created_at, updated_at
                    ) VALUES (?, ?, 'romanpics', ?, ?, ?, 'webp', 1, ?, ?, ?, ?, ?,
                              'preview', ?, ?, ?)
                    ON CONFLICT (item_id, url) DO UPDATE SET
                        width = excluded.width, height = excluded.height,
                        recipe = excluded.recipe, alt_text = excluded.alt_text,
                        credit = excluded.credit, rights = excluded.rights,
                        rights_url = excluded.rights_url,
                        last_verified_at = excluded.last_verified_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        rendition_id,
                        payload["item_id"],
                        url,
                        preview["width"],
                        preview["height"],
                        recipe_json,
                        result["alt_text"],
                        result["credit"],
                        result.get("rights"),
                        result.get("rights_url"),
                        now,
                        now,
                        now,
                    ),
                )
            metadata = _json_object(item["metadata_json"])
            publish = (
                item["editorial_state"] == "draft" and metadata.get("publication_gate") == "render"
            )
            if publish:
                metadata.pop("publication_gate", None)
                connection.execute(
                    """
                    UPDATE gallery_item
                    SET editorial_state = 'published', metadata_json = ?,
                        processing_note = CASE
                            WHEN processing_note = ? THEN NULL ELSE processing_note
                        END,
                        updated_at = ?
                    WHERE id = ? AND editorial_state = 'draft'
                    """,
                    (json.dumps(metadata), RENDER_PENDING_NOTE, now, payload["item_id"]),
                )
            dedupe_key = f"embed:{payload['item_id']}:{item['checksum']}"
            embed_job_id = _stable_uuid("job", dedupe_key)
            embed_payload = {
                "item_id": payload["item_id"],
                "source_record_id": item["source_record_id"],
                "checksum": item["checksum"],
            }
            connection.execute(
                """
                INSERT OR IGNORE INTO jobs (
                    id, job_type, payload_json, status, priority, attempts,
                    max_attempts, available_at, dedupe_key, created_at, updated_at
                ) VALUES (?, 'embed', ?, 'queued', 10, 0, 5, ?, ?, ?, ?)
                """,
                (embed_job_id, json.dumps(embed_payload), now, dedupe_key, now, now),
            )
            existing = connection.execute(
                "SELECT id FROM jobs WHERE dedupe_key = ?", (dedupe_key,)
            ).fetchone()
            connection.execute("COMMIT")
            return {
                "published": publish,
                "embed_job_id": str(existing["id"]),
                "rendition_count": len(previews),
            }
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def persist_embedding(
        self, payload: EmbedPayload, result: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        model, version, vector, perceptual_hash = _embedding_result(result)
        now = datetime.now(UTC).isoformat()
        connection = sqlite3.connect(self.database, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN IMMEDIATE")
        try:
            current = connection.execute(
                """
                SELECT item.id FROM gallery_item AS item
                JOIN source_record AS record ON record.id = item.primary_source_record_id
                WHERE item.id = ? AND record.id = ? AND record.checksum = ?
                  AND record.state = 'active'
                """,
                (payload["item_id"], payload["source_record_id"], payload["checksum"]),
            ).fetchone()
            if current is None:
                raise LookupError("embedding result is stale for the current source record")
            embedding_id = _stable_uuid("embedding", f"{payload['item_id']}:{model}:{version}")
            connection.execute(
                """
                INSERT INTO embedding (
                    id, item_id, model, version, vector, perceptual_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (item_id, model, version) DO UPDATE SET
                    vector = excluded.vector, perceptual_hash = excluded.perceptual_hash,
                    updated_at = excluded.updated_at
                """,
                (
                    embedding_id,
                    payload["item_id"],
                    model,
                    version,
                    json.dumps(vector),
                    perceptual_hash,
                    now,
                    now,
                ),
            )
            connection.execute("COMMIT")
            return {"embedding_id": embedding_id, "model": model, "version": version}
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def persist_clusters(
        self, payload: ClusterPayload, result: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        algorithm_version, groups, edges = _cluster_inputs(result)
        now = datetime.now(UTC).isoformat()
        connection = sqlite3.connect(self.database, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN IMMEDIATE")
        try:
            run = connection.execute(
                "SELECT id FROM ingest_run WHERE id = ? AND source_id = ?",
                (payload["ingest_run_id"], payload["source_id"]),
            ).fetchone()
            if run is None:
                raise LookupError("cluster ingest run no longer belongs to the requested source")
            previous = _previous_snapshot(
                connection.execute(
                    """
                    SELECT cluster.id AS cluster_id, member.item_id,
                           cluster.created_at, cluster.updated_at
                    FROM cluster
                    JOIN cluster_member AS member ON member.cluster_id = cluster.id
                    WHERE cluster.archived_at IS NULL
                    ORDER BY cluster.id, member.item_id
                    """
                ).fetchall()
            )
            reconciliation = StableClusterReconciler().reconcile(
                previous, groups, run_id=payload["ingest_run_id"]
            )
            member_ids = sorted({member for group in groups for member in group})
            classes: dict[str, str] = {}
            if member_ids:
                placeholders = ",".join("?" for _ in member_ids)
                rows = connection.execute(
                    f"""
                    SELECT item.id, item.content_class
                    FROM gallery_item AS item
                    JOIN source_record AS record ON record.id = item.primary_source_record_id
                    WHERE item.id IN ({placeholders})
                      AND item.editorial_state = 'published' AND record.state = 'active'
                    """,
                    member_ids,
                ).fetchall()
                classes = {str(row["id"]): str(row["content_class"]) for row in rows}
            if set(classes) != set(member_ids):
                raise LookupError("cluster result contains a missing, hidden, or inactive item")

            existing_ids = {
                str(row["id"]) for row in connection.execute("SELECT id FROM cluster").fetchall()
            }
            identifiers = {
                cluster.cluster_id: (
                    cluster.cluster_id
                    if cluster.cluster_id in existing_ids
                    else _stable_uuid("cluster", cluster.cluster_id)
                )
                for cluster in reconciliation.snapshot.active
            }
            active_ids: set[str] = set()
            score_by_pair = {
                (str(edge["left"]), str(edge["right"])): float(edge["score"]) for edge in edges
            }
            for cluster in reconciliation.snapshot.active:
                cluster_id = identifiers[cluster.cluster_id]
                active_ids.add(cluster_id)
                members = sorted(cluster.members)
                content_classes = {classes[member] for member in members}
                if len(content_classes) != 1:
                    raise RuntimeError("similarity cluster crossed a content-class boundary")
                content_class = next(iter(content_classes))
                representative = members[0]
                existing = connection.execute(
                    "SELECT slug, title, summary, created_at FROM cluster WHERE id = ?",
                    (cluster_id,),
                ).fetchone()
                slug = str(existing["slug"]) if existing else cluster.cluster_id
                title = (
                    str(existing["title"])
                    if existing
                    else f"Related {content_class.replace('_', ' ').title()} images"
                )
                summary = (
                    str(existing["summary"])
                    if existing
                    else "Automatically grouped by visual similarity within one content class."
                )
                created_at = str(existing["created_at"]) if existing else now
                connection.execute(
                    """
                    INSERT INTO cluster (
                        id, slug, title, summary, content_class, algorithm_version,
                        representative_item_id, centroid, archived_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
                    ON CONFLICT (id) DO UPDATE SET
                        content_class = excluded.content_class,
                        algorithm_version = excluded.algorithm_version,
                        representative_item_id = excluded.representative_item_id,
                        centroid = NULL, archived_at = NULL, updated_at = excluded.updated_at
                    """,
                    (
                        cluster_id,
                        slug,
                        title,
                        summary,
                        content_class,
                        algorithm_version,
                        representative,
                        created_at,
                        now,
                    ),
                )
                connection.execute("DELETE FROM cluster_member WHERE cluster_id = ?", (cluster_id,))

                ordered = sorted(
                    members,
                    key=lambda item_id: (
                        item_id != representative,
                        -_member_score(item_id, representative, cluster.members, score_by_pair),
                        item_id,
                    ),
                )
                for rank, item_id in enumerate(ordered):
                    connection.execute(
                        """INSERT INTO cluster_member
                           (cluster_id, item_id, similarity, rank) VALUES (?, ?, ?, ?)""",
                        (
                            cluster_id,
                            item_id,
                            _member_score(item_id, representative, cluster.members, score_by_pair),
                            rank,
                        ),
                    )

            currently_active = {
                str(row["id"])
                for row in connection.execute(
                    "SELECT id FROM cluster WHERE archived_at IS NULL"
                ).fetchall()
            }
            archived_ids = currently_active - active_ids
            for cluster_id in archived_ids:
                connection.execute(
                    "UPDATE cluster SET archived_at = ?, updated_at = ? WHERE id = ?",
                    (now, now, cluster_id),
                )

            # The public API does not select a similarity algorithm version, so stale
            # edges must not remain visible alongside the current graph.
            connection.execute("DELETE FROM similarity_edge")
            directional_edges = 0
            for edge in edges:
                for left, right in (
                    (str(edge["left"]), str(edge["right"])),
                    (str(edge["right"]), str(edge["left"])),
                ):
                    edge_id = _stable_uuid("similarity", f"{left}:{right}:{algorithm_version}")
                    connection.execute(
                        """
                        INSERT INTO similarity_edge (
                            id, item_id, related_item_id, score, reasons, algorithm_version
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            edge_id,
                            left,
                            right,
                            edge["score"],
                            json.dumps([edge["reason"]]),
                            algorithm_version,
                        ),
                    )
                    directional_edges += 1
            connection.execute("COMMIT")
            return {
                "algorithm_version": algorithm_version,
                **_mapped_reconciliation(
                    reconciliation.snapshot,
                    reconciliation.archived,
                    reconciliation.lineage,
                    identifiers,
                ),
                "active_cluster_count": len(active_ids),
                "archived_cluster_count": len(archived_ids),
                "edge_count": directional_edges,
            }
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def persist_link_checks(
        self, payload: LinkCheckPayload, result: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        if payload["scope"] != "catalog":
            raise ValueError("jobs-v1 currently supports only the catalog link-check scope")
        job_id, checks = _checks(result)
        now = datetime.now(UTC).isoformat()
        connection = sqlite3.connect(self.database, isolation_level=None)
        connection.execute("BEGIN IMMEDIATE")
        try:
            for check in checks:
                row_id = _stable_uuid(
                    "link-check",
                    f"{job_id}:{check['target_kind']}:{check['target_id']}:{check['url']}",
                )
                connection.execute(
                    """
                    INSERT INTO link_check (
                        id, url, target_kind, target_id, ok, status_code,
                        final_url, error, checked_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (id) DO UPDATE SET
                        ok = excluded.ok, status_code = excluded.status_code,
                        final_url = excluded.final_url, error = excluded.error,
                        checked_at = excluded.checked_at
                    """,
                    (
                        row_id,
                        check["url"],
                        check["target_kind"],
                        check["target_id"],
                        int(check["ok"]),
                        check["status_code"],
                        check["final_url"],
                        check["error"],
                        now,
                    ),
                )
            connection.execute("COMMIT")
            return {"persisted": len(checks)}
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()


class PostgresCatalogResolver(_CatalogResolver):
    def __init__(self, database_url: str, *, search_path: str | None = None):
        self.database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        self.search_path = search_path

    def _connect(self):
        import psycopg
        from psycopg import sql
        from psycopg.rows import dict_row

        connection = psycopg.connect(self.database_url, row_factory=dict_row)
        if self.search_path:
            connection.execute(
                sql.SQL("SET search_path TO {}").format(sql.Identifier(self.search_path))
            )
        return connection

    def _rows(self, query: str, parameters: tuple[Any, ...]) -> list[Mapping[str, Any]]:
        try:
            import psycopg  # noqa: F401
        except ImportError as error:
            raise RuntimeError("psycopg 3 is required for PostgreSQL catalog resolution") from error
        with (
            self._connect() as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(query, parameters)
            return list(cursor.fetchall())

    def persist_render(
        self, payload: RenderPayload, result: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        previews = _public_previews(result)
        try:
            import psycopg  # noqa: F401
            from psycopg.types.json import Jsonb
        except ImportError as error:
            raise RuntimeError("psycopg 3 is required for PostgreSQL result persistence") from error

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    SELECT item.editorial_state, item.metadata_json, item.processing_note,
                           item.alt_text, record.id AS source_record_id, record.checksum
                    FROM gallery_item AS item
                    JOIN source_record AS record ON record.id = item.primary_source_record_id
                    JOIN item_asset AS asset ON asset.item_id = item.id
                    WHERE item.id = %s AND asset.product_id = %s AND record.state = 'active'
                    LIMIT 1
                    FOR UPDATE OF item
                    """,
                (payload["item_id"], payload["product_id"]),
            )
            item = cursor.fetchone()
            if item is None:
                raise LookupError("render result no longer matches an active catalog item/product")
            recipe_json = json.dumps(payload["recipe"], sort_keys=True, separators=(",", ":"))
            for preview in previews:
                url = str(preview["public_url"])
                rendition_id = _stable_uuid("rendition", f"{payload['item_id']}:{url}")
                cursor.execute(
                    """
                        INSERT INTO rendition (
                            id, item_id, provider, url, width, height, format,
                            is_site_derivative, recipe, alt_text, credit, rights,
                            rights_url, role, last_verified_at, created_at, updated_at
                        ) VALUES (%s, %s, 'romanpics', %s, %s, %s, 'webp', true,
                                  %s, %s, %s, %s, %s, 'preview', CURRENT_TIMESTAMP,
                                  CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        ON CONFLICT (item_id, url) DO UPDATE SET
                            width = excluded.width, height = excluded.height,
                            recipe = excluded.recipe, alt_text = excluded.alt_text,
                            credit = excluded.credit, rights = excluded.rights,
                            rights_url = excluded.rights_url,
                            last_verified_at = excluded.last_verified_at,
                            updated_at = excluded.updated_at
                        """,
                    (
                        rendition_id,
                        payload["item_id"],
                        url,
                        preview["width"],
                        preview["height"],
                        recipe_json,
                        result["alt_text"],
                        result["credit"],
                        result.get("rights"),
                        result.get("rights_url"),
                    ),
                )
            metadata = _json_object(item["metadata_json"])
            publish = (
                item["editorial_state"] == "draft" and metadata.get("publication_gate") == "render"
            )
            if publish:
                metadata.pop("publication_gate", None)
                cursor.execute(
                    """
                        UPDATE gallery_item
                        SET editorial_state = 'published', metadata_json = %s,
                            processing_note = CASE
                                WHEN processing_note = %s THEN NULL ELSE processing_note
                            END,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s AND editorial_state = 'draft'
                        """,
                    (Jsonb(metadata), RENDER_PENDING_NOTE, payload["item_id"]),
                )
            dedupe_key = f"embed:{payload['item_id']}:{item['checksum']}"
            proposed_job_id = _stable_uuid("job", dedupe_key)
            embed_payload = {
                "item_id": payload["item_id"],
                "source_record_id": item["source_record_id"],
                "checksum": item["checksum"],
            }
            cursor.execute(
                """
                    INSERT INTO jobs (
                        id, job_type, payload_json, status, priority, attempts,
                        max_attempts, available_at, dedupe_key, created_at, updated_at
                    ) VALUES (%s, 'embed', %s, 'queued', 10, 0, 5,
                              CURRENT_TIMESTAMP, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (dedupe_key) DO NOTHING
                    RETURNING id
                    """,
                (proposed_job_id, Jsonb(embed_payload), dedupe_key),
            )
            embed_job = cursor.fetchone()
            if embed_job is None:
                cursor.execute("SELECT id FROM jobs WHERE dedupe_key = %s", (dedupe_key,))
                embed_job = cursor.fetchone()
            if embed_job is None:
                raise RuntimeError("failed to enqueue embedding after rendering")
            return {
                "published": publish,
                "embed_job_id": str(embed_job["id"]),
                "rendition_count": len(previews),
            }

    def persist_embedding(
        self, payload: EmbedPayload, result: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        model, version, vector, perceptual_hash = _embedding_result(result)
        try:
            import psycopg  # noqa: F401
            from psycopg.types.json import Jsonb
        except ImportError as error:
            raise RuntimeError("psycopg 3 is required for PostgreSQL result persistence") from error

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    SELECT item.id
                    FROM gallery_item AS item
                    JOIN source_record AS record ON record.id = item.primary_source_record_id
                    WHERE item.id = %s AND record.id = %s AND record.checksum = %s
                      AND record.state = 'active'
                    FOR UPDATE OF item
                    """,
                (payload["item_id"], payload["source_record_id"], payload["checksum"]),
            )
            if cursor.fetchone() is None:
                raise LookupError("embedding result is stale for the current source record")
            embedding_id = _stable_uuid("embedding", f"{payload['item_id']}:{model}:{version}")
            cursor.execute(
                """
                    INSERT INTO embedding (
                        id, item_id, model, version, vector, perceptual_hash,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s,
                              CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (item_id, model, version) DO UPDATE SET
                        vector = excluded.vector,
                        perceptual_hash = excluded.perceptual_hash,
                        updated_at = excluded.updated_at
                    """,
                (
                    embedding_id,
                    payload["item_id"],
                    model,
                    version,
                    Jsonb(vector),
                    perceptual_hash,
                ),
            )
            return {"embedding_id": embedding_id, "model": model, "version": version}

    def persist_clusters(
        self, payload: ClusterPayload, result: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        algorithm_version, groups, edges = _cluster_inputs(result)
        try:
            import psycopg  # noqa: F401
            from psycopg.types.json import Jsonb
        except ImportError as error:
            raise RuntimeError("psycopg 3 is required for PostgreSQL result persistence") from error

        with self._connect() as connection, connection.cursor() as cursor:
            # Resolve, reconcile, and replace one global graph serially. This avoids
            # two source-triggered refreshes inheriting the same prior snapshot.
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext('romanpics-cluster-refresh'))")
            cursor.execute(
                "SELECT id FROM ingest_run WHERE id = %s AND source_id = %s",
                (payload["ingest_run_id"], payload["source_id"]),
            )
            if cursor.fetchone() is None:
                raise LookupError("cluster ingest run no longer belongs to the requested source")
            cursor.execute(
                """
                SELECT cluster.id AS cluster_id, member.item_id,
                       cluster.created_at, cluster.updated_at
                FROM cluster
                JOIN cluster_member AS member ON member.cluster_id = cluster.id
                WHERE cluster.archived_at IS NULL
                ORDER BY cluster.id, member.item_id
                """
            )
            previous = _previous_snapshot(cursor.fetchall())
            reconciliation = StableClusterReconciler().reconcile(
                previous, groups, run_id=payload["ingest_run_id"]
            )
            member_ids = sorted({member for group in groups for member in group})
            classes: dict[str, str] = {}
            if member_ids:
                cursor.execute(
                    """
                    SELECT item.id, item.content_class
                    FROM gallery_item AS item
                    JOIN source_record AS record ON record.id = item.primary_source_record_id
                    WHERE item.id = ANY(%s)
                      AND item.editorial_state = 'published' AND record.state = 'active'
                    """,
                    (member_ids,),
                )
                classes = {str(row["id"]): str(row["content_class"]) for row in cursor.fetchall()}
            if set(classes) != set(member_ids):
                raise LookupError("cluster result contains a missing, hidden, or inactive item")

            cursor.execute("SELECT id FROM cluster")
            existing_ids = {str(row["id"]) for row in cursor.fetchall()}
            identifiers = {
                cluster.cluster_id: (
                    cluster.cluster_id
                    if cluster.cluster_id in existing_ids
                    else _stable_uuid("cluster", cluster.cluster_id)
                )
                for cluster in reconciliation.snapshot.active
            }
            active_ids: set[str] = set()
            score_by_pair = {
                (str(edge["left"]), str(edge["right"])): float(edge["score"]) for edge in edges
            }
            for cluster in reconciliation.snapshot.active:
                cluster_id = identifiers[cluster.cluster_id]
                active_ids.add(cluster_id)
                members = sorted(cluster.members)
                content_classes = {classes[member] for member in members}
                if len(content_classes) != 1:
                    raise RuntimeError("similarity cluster crossed a content-class boundary")
                content_class = next(iter(content_classes))
                representative = members[0]
                cursor.execute(
                    "SELECT slug, title, summary, created_at FROM cluster WHERE id = %s",
                    (cluster_id,),
                )
                existing = cursor.fetchone()
                slug = str(existing["slug"]) if existing else cluster.cluster_id
                title = (
                    str(existing["title"])
                    if existing
                    else f"Related {content_class.replace('_', ' ').title()} images"
                )
                summary = (
                    str(existing["summary"])
                    if existing
                    else "Automatically grouped by visual similarity within one content class."
                )
                created_at = existing["created_at"] if existing else datetime.now(UTC)
                cursor.execute(
                    """
                    INSERT INTO cluster (
                        id, slug, title, summary, content_class, algorithm_version,
                        representative_item_id, centroid, archived_at, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, NULL, %s,
                              CURRENT_TIMESTAMP)
                    ON CONFLICT (id) DO UPDATE SET
                        content_class = excluded.content_class,
                        algorithm_version = excluded.algorithm_version,
                        representative_item_id = excluded.representative_item_id,
                        centroid = NULL, archived_at = NULL, updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        cluster_id,
                        slug,
                        title,
                        summary,
                        content_class,
                        algorithm_version,
                        representative,
                        created_at,
                    ),
                )
                cursor.execute("DELETE FROM cluster_member WHERE cluster_id = %s", (cluster_id,))

                ordered = sorted(
                    members,
                    key=lambda item_id: (
                        item_id != representative,
                        -_member_score(item_id, representative, cluster.members, score_by_pair),
                        item_id,
                    ),
                )
                for rank, item_id in enumerate(ordered):
                    cursor.execute(
                        """INSERT INTO cluster_member
                           (cluster_id, item_id, similarity, rank) VALUES (%s, %s, %s, %s)""",
                        (
                            cluster_id,
                            item_id,
                            _member_score(item_id, representative, cluster.members, score_by_pair),
                            rank,
                        ),
                    )

            cursor.execute("SELECT id FROM cluster WHERE archived_at IS NULL")
            currently_active = {str(row["id"]) for row in cursor.fetchall()}
            archived_ids = currently_active - active_ids
            for cluster_id in archived_ids:
                cursor.execute(
                    """UPDATE cluster SET archived_at = CURRENT_TIMESTAMP,
                       updated_at = CURRENT_TIMESTAMP WHERE id = %s""",
                    (cluster_id,),
                )

            cursor.execute("DELETE FROM similarity_edge")
            directional_edges = 0
            for edge in edges:
                for left, right in (
                    (str(edge["left"]), str(edge["right"])),
                    (str(edge["right"]), str(edge["left"])),
                ):
                    edge_id = _stable_uuid("similarity", f"{left}:{right}:{algorithm_version}")
                    cursor.execute(
                        """
                        INSERT INTO similarity_edge (
                            id, item_id, related_item_id, score, reasons, algorithm_version
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            edge_id,
                            left,
                            right,
                            edge["score"],
                            Jsonb([edge["reason"]]),
                            algorithm_version,
                        ),
                    )
                    directional_edges += 1
            return {
                "algorithm_version": algorithm_version,
                **_mapped_reconciliation(
                    reconciliation.snapshot,
                    reconciliation.archived,
                    reconciliation.lineage,
                    identifiers,
                ),
                "active_cluster_count": len(active_ids),
                "archived_cluster_count": len(archived_ids),
                "edge_count": directional_edges,
            }

    def persist_link_checks(
        self, payload: LinkCheckPayload, result: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        if payload["scope"] != "catalog":
            raise ValueError("jobs-v1 currently supports only the catalog link-check scope")
        job_id, checks = _checks(result)
        with self._connect() as connection, connection.cursor() as cursor:
            for check in checks:
                row_id = _stable_uuid(
                    "link-check",
                    f"{job_id}:{check['target_kind']}:{check['target_id']}:{check['url']}",
                )
                cursor.execute(
                    """
                    INSERT INTO link_check (
                        id, url, target_kind, target_id, ok, status_code,
                        final_url, error, checked_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (id) DO UPDATE SET
                        ok = excluded.ok, status_code = excluded.status_code,
                        final_url = excluded.final_url, error = excluded.error,
                        checked_at = excluded.checked_at
                    """,
                    (
                        row_id,
                        check["url"],
                        check["target_kind"],
                        check["target_id"],
                        check["ok"],
                        check["status_code"],
                        check["final_url"],
                        check["error"],
                    ),
                )
            return {"persisted": len(checks)}
