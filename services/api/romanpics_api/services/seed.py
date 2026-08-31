from __future__ import annotations

from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from ..adapters import StaticCatalogAdapter
from ..models import (
    Cluster,
    ClusterMember,
    Collection,
    CollectionItem,
    GalleryItem,
    SimilarityEdge,
    stable_uuid,
)
from .ingestion import IngestionService


async def seed_catalog(
    session_factory: sessionmaker[Session],
    path: str | Path,
    allowed_hosts: tuple[str, ...],
) -> dict[str, int | str]:
    """Idempotently rebuild the checked-in launch-era fixture graph."""
    path = Path(path)
    adapter = StaticCatalogAdapter(path)
    run = await IngestionService(session_factory, allowed_hosts).sync(adapter, full=True)
    payload = adapter._load()
    session = session_factory()
    try:
        items = {item.slug: item for item in session.scalars(select(GalleryItem)).all()}
        computed_graph_exists = (
            session.scalar(
                select(Cluster.id)
                .where(Cluster.algorithm_version.not_like("fixture%"))
                .limit(1)
            )
            is not None
            or session.scalar(
                select(SimilarityEdge.id)
                .where(SimilarityEdge.algorithm_version.not_like("fixture%"))
                .limit(1)
            )
            is not None
        )
        cluster_count = (
            0
            if computed_graph_exists
            else _seed_clusters(session, payload.get("clusters", []), items)
        )
        collection_count = _seed_collections(session, payload.get("collections", []), items)
        similarity_count = (
            0
            if computed_graph_exists
            else _seed_similarities(session, payload.get("similarities", []), items)
        )
        session.commit()
        return {
            "run_id": run.id,
            "items": len(payload.get("records", [])),
            "clusters": cluster_count,
            "collections": collection_count,
            "similarities": similarity_count,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _seed_clusters(
    session: Session, definitions: list[dict[str, object]], items: dict[str, GalleryItem]
) -> int:
    for definition in definitions:
        slug = str(definition["slug"])
        cluster = session.scalar(select(Cluster).where(Cluster.slug == slug))
        if cluster is None:
            cluster = Cluster(
                id=stable_uuid("cluster", slug),
                slug=slug,
                title=str(definition["title"]),
                summary=str(definition["summary"]),
                content_class=str(definition["content_class"]),
                algorithm_version=str(definition.get("algorithm_version", "fixture-v1")),
            )
            session.add(cluster)
            session.flush()
        cluster.title = str(definition["title"])
        cluster.summary = str(definition["summary"])
        cluster.content_class = str(definition["content_class"])
        cluster.algorithm_version = str(definition.get("algorithm_version", "fixture-v1"))
        cluster.archived_at = None
        representative_slug = str(definition.get("representative") or "")
        cluster.representative_item_id = _require_item(items, representative_slug).id
        session.execute(delete(ClusterMember).where(ClusterMember.cluster_id == cluster.id))
        for position, item_slug in enumerate(definition.get("items", [])):
            item = _require_item(items, str(item_slug))
            if item.content_class != cluster.content_class:
                raise ValueError(
                    f"cluster {slug} mixes {cluster.content_class} with {item.content_class}"
                )
            session.add(
                ClusterMember(
                    cluster_id=cluster.id,
                    item_id=item.id,
                    similarity=max(0.0, 1.0 - position * 0.05),
                    rank=position,
                )
            )
    return len(definitions)


def _seed_collections(
    session: Session, definitions: list[dict[str, object]], items: dict[str, GalleryItem]
) -> int:
    for definition in definitions:
        slug = str(definition["slug"])
        collection = session.scalar(select(Collection).where(Collection.slug == slug))
        if collection is None:
            collection = Collection(
                id=stable_uuid("collection", slug),
                slug=slug,
                title=str(definition["title"]),
                summary=str(definition["summary"]),
            )
            session.add(collection)
            session.flush()
        collection.title = str(definition["title"])
        collection.summary = str(definition["summary"])
        collection.published = bool(definition.get("published", True))
        session.execute(delete(CollectionItem).where(CollectionItem.collection_id == collection.id))
        for position, item_slug in enumerate(definition.get("items", [])):
            session.add(
                CollectionItem(
                    collection_id=collection.id,
                    item_id=_require_item(items, str(item_slug)).id,
                    position=position,
                )
            )
    return len(definitions)


def _seed_similarities(
    session: Session, definitions: list[dict[str, object]], items: dict[str, GalleryItem]
) -> int:
    count = 0
    for definition in definitions:
        left = _require_item(items, str(definition["from"]))
        right = _require_item(items, str(definition["to"]))
        for origin, related in ((left, right), (right, left)):
            version = str(definition.get("algorithm_version", "fixture-v1"))
            row = session.scalar(
                select(SimilarityEdge).where(
                    SimilarityEdge.item_id == origin.id,
                    SimilarityEdge.related_item_id == related.id,
                    SimilarityEdge.algorithm_version == version,
                )
            )
            if row is None:
                row = SimilarityEdge(
                    id=stable_uuid("similarity", f"{origin.id}:{related.id}:{version}"),
                    item_id=origin.id,
                    related_item_id=related.id,
                    algorithm_version=version,
                    score=float(definition.get("score", 0.8)),
                )
                session.add(row)
            row.score = float(definition.get("score", 0.8))
            row.reasons = list(definition.get("reasons", ["metadata"]))
            count += 1
    return count


def _require_item(items: dict[str, GalleryItem], slug: str) -> GalleryItem:
    try:
        return items[slug]
    except KeyError:
        raise ValueError(f"seed graph refers to unknown item slug: {slug}") from None
