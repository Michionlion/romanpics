from __future__ import annotations

import math
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import and_, case, desc, func, or_, select
from sqlalchemy.orm import Session

from ..models import (
    ActiveVote,
    ArchiveProduct,
    Cluster,
    ClusterMember,
    Collection,
    CollectionItem,
    GalleryItem,
    ItemAsset,
    ItemTag,
    Observation,
    Rendition,
    SimilarityEdge,
    Source,
    SourceRecord,
    Tag,
    VoteTotal,
)
from ..schemas import (
    ArchiveProductOut,
    ClusterOut,
    GalleryItemOut,
    ItemDetailOut,
    ObservationOut,
    RenditionOut,
    SourceOut,
)


def get_item_row(session: Session, identifier: str) -> GalleryItem | None:
    clauses = [GalleryItem.slug == identifier]
    try:
        uuid.UUID(identifier)
        clauses.append(GalleryItem.id == identifier)
    except ValueError:
        pass
    return session.scalar(
        select(GalleryItem).where(or_(*clauses), GalleryItem.editorial_state == "published")
    )


def item_query(
    *,
    q: str | None = None,
    content_class: str | None = None,
    flight_only: bool | None = None,
    instrument: str | None = None,
    survey: str | None = None,
    optical_element: str | None = None,
    target: str | None = None,
    tag: str | None = None,
    published_from: date | None = None,
    published_to: date | None = None,
    cluster: str | None = None,
):
    statement = (
        select(GalleryItem)
        .join(SourceRecord, GalleryItem.primary_source_record_id == SourceRecord.id)
        .where(
            GalleryItem.editorial_state == "published",
            SourceRecord.state == "active",
        )
    )
    if q:
        escaped = q.lower().replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(GalleryItem.search_document.ilike(f"%{escaped}%", escape="\\"))
    if content_class:
        statement = statement.where(GalleryItem.content_class == content_class)
    if tag:
        statement = (
            statement.join(ItemTag, ItemTag.item_id == GalleryItem.id)
            .join(Tag, Tag.id == ItemTag.tag_id)
            .where(or_(Tag.slug == tag.lower(), func.lower(Tag.label) == tag.lower()))
        )
    if flight_only is True:
        statement = statement.where(GalleryItem.is_flight_data.is_(True))
    if any((instrument, survey, optical_element, target)):
        statement = statement.join(
            Observation, GalleryItem.primary_observation_id == Observation.id
        )
        if instrument:
            statement = statement.where(func.lower(Observation.instrument) == instrument.lower())
        if survey:
            statement = statement.where(func.lower(Observation.survey) == survey.lower())
        if target:
            statement = statement.where(Observation.target_name.ilike(f"%{target}%"))
        if optical_element:
            # JSON containment syntax varies. A quoted substring is portable for
            # the compact string-array representation used by both dialects.
            statement = statement.where(
                func.lower(func.cast(Observation.optical_elements, String)).contains(
                    f'"{optical_element.lower()}"'
                )
            )
    if published_from:
        statement = statement.where(
            GalleryItem.published_at >= datetime.combine(published_from, datetime.min.time(), UTC)
        )
    if published_to:
        statement = statement.where(
            GalleryItem.published_at
            < datetime.combine(published_to, datetime.min.time(), UTC) + _one_day()
        )
    if cluster:
        statement = (
            statement.join(ClusterMember)
            .join(Cluster)
            .where(or_(Cluster.id == cluster, Cluster.slug == cluster))
        )
    return statement


def apply_item_sort(statement: Any, sort: str, q: str | None = None):
    if sort in {"top", "trending"}:
        statement = statement.outerjoin(
            VoteTotal,
            and_(VoteTotal.target_kind == "item", VoteTotal.target_id == GalleryItem.id),
        ).order_by(desc(func.coalesce(VoteTotal.count, 0)), desc(GalleryItem.published_at))
    elif sort == "relevance" and q:
        statement = statement.order_by(
            desc(case((func.lower(GalleryItem.title).contains(q.lower()), 1), else_=0)),
            desc(GalleryItem.published_at),
        )
    else:
        statement = statement.order_by(desc(GalleryItem.published_at), GalleryItem.id)
    return statement


def within_cone(item: GalleryItem, session: Session, ra: float, dec: float, radius: float) -> bool:
    if not item.primary_observation_id:
        return False
    observation = session.get(Observation, item.primary_observation_id)
    if observation is None or observation.ra is None or observation.dec is None:
        return False
    ra1, dec1, ra2, dec2 = map(math.radians, (ra, dec, observation.ra, observation.dec))
    cosine = math.sin(dec1) * math.sin(dec2) + math.cos(dec1) * math.cos(dec2) * math.cos(ra1 - ra2)
    distance = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
    return distance <= radius


def serialize_item(session: Session, item: GalleryItem, actor_id: str | None) -> GalleryItemOut:
    source_record = session.get(SourceRecord, item.primary_source_record_id)
    source = session.get(Source, source_record.source_id)
    preview = session.scalar(
        select(Rendition)
        .where(Rendition.item_id == item.id)
        .order_by(case((Rendition.role == "preview", 0), else_=1), Rendition.width)
    )
    if preview is None:
        raise RuntimeError(f"published item {item.id} has no rendition")
    tags = session.scalars(
        select(Tag.label)
        .join(ItemTag, ItemTag.tag_id == Tag.id)
        .where(ItemTag.item_id == item.id)
        .order_by(Tag.label)
    ).all()
    cluster_id = session.scalar(
        select(ClusterMember.cluster_id)
        .join(Cluster, Cluster.id == ClusterMember.cluster_id)
        .where(ClusterMember.item_id == item.id, Cluster.archived_at.is_(None))
        .order_by(ClusterMember.rank)
    )
    vote_count = _vote_count(session, "item", item.id)
    has_voted = _has_voted(session, actor_id, "item", item.id)
    observation = (
        session.get(Observation, item.primary_observation_id)
        if item.primary_observation_id
        else None
    )
    provider = str(item.metadata_json.get("provider") or source.adapter.upper())
    return GalleryItemOut(
        id=item.id,
        slug=item.slug,
        title=item.title,
        summary=item.plain_summary,
        content_class=item.content_class,
        is_flight_data=item.is_flight_data,
        published_at=item.published_at,
        observed_at=observation.observed_start if observation else None,
        source=SourceOut(
            provider=provider,
            external_id=source_record.external_id,
            source_url=source_record.canonical_url,
            archive_record_url=source_record.canonical_url if observation else None,
            credit=preview.credit,
            rights=preview.rights,
            rights_url=preview.rights_url,
        ),
        preview=RenditionOut(
            url=preview.url,
            width=preview.width,
            height=preview.height,
            format=preview.format,
            provider=preview.provider,
            site_generated=preview.is_site_derivative,
            transformation=preview.recipe,
        ),
        alt_text=item.alt_text,
        tags=list(tags),
        vote_count=vote_count,
        viewer_has_voted=has_voted,
        cluster_id=cluster_id,
    )


def serialize_item_detail(
    session: Session, item: GalleryItem, actor_id: str | None
) -> ItemDetailOut:
    base = serialize_item(session, item, actor_id).model_dump()
    products = products_for_item(session, item.id)
    observation = (
        session.get(Observation, item.primary_observation_id)
        if item.primary_observation_id
        else None
    )
    source_record = session.get(SourceRecord, item.primary_source_record_id)
    return ItemDetailOut(
        **base,
        originals=[serialize_product(product) for product in products],
        observation=serialize_observation(observation),
        processing_note=item.processing_note,
        superseded_by=source_record.superseded_by_id,
    )


def products_for_item(session: Session, item_id: str) -> list[ArchiveProduct]:
    return list(
        session.scalars(
            select(ArchiveProduct)
            .join(ItemAsset, ItemAsset.product_id == ArchiveProduct.id)
            .where(ItemAsset.item_id == item_id)
            .order_by(ItemAsset.position, ArchiveProduct.id)
        ).all()
    )


def serialize_product(product: ArchiveProduct) -> ArchiveProductOut:
    return ArchiveProductOut(
        id=product.id,
        url=product.external_url,
        subtype=product.subtype,
        media_type=product.media_type,
        byte_size=product.byte_size,
        data_level=product.data_level,
        active=product.active,
        superseded_by=product.superseded_by_id,
    )


def serialize_observation(observation: Observation | None) -> ObservationOut | None:
    if observation is None:
        return None
    return ObservationOut(
        observation_id=observation.observation_id,
        program_id=observation.program_id,
        survey=observation.survey,
        instrument=observation.instrument,
        mode=observation.mode,
        optical_elements=observation.optical_elements,
        target=observation.target_name,
        ra=observation.ra,
        dec=observation.dec,
        data_level=observation.data_level,
        release_name=observation.release_name,
        pipeline_version=observation.pipeline_version,
    )


def serialize_cluster(session: Session, cluster: Cluster, actor_id: str | None) -> ClusterOut:
    representative = session.get(GalleryItem, cluster.representative_item_id)
    if representative is None:
        representative = session.scalar(
            select(GalleryItem)
            .join(ClusterMember)
            .where(ClusterMember.cluster_id == cluster.id)
            .order_by(ClusterMember.rank)
        )
    if representative is None:
        raise RuntimeError(f"cluster {cluster.id} has no representative")
    item_count = (
        session.scalar(
            select(func.count(ClusterMember.item_id)).where(ClusterMember.cluster_id == cluster.id)
        )
        or 0
    )
    return ClusterOut(
        id=cluster.id,
        slug=cluster.slug,
        title=cluster.title,
        summary=cluster.summary,
        content_class=cluster.content_class,
        representative=serialize_item(session, representative, actor_id),
        item_count=item_count,
        vote_count=_vote_count(session, "cluster", cluster.id),
        viewer_has_voted=_has_voted(session, actor_id, "cluster", cluster.id),
        version=cluster.algorithm_version,
        archived_at=cluster.archived_at,
    )


def collection_items(session: Session, collection: Collection) -> list[GalleryItem]:
    return list(
        session.scalars(
            select(GalleryItem)
            .join(CollectionItem, CollectionItem.item_id == GalleryItem.id)
            .where(
                CollectionItem.collection_id == collection.id,
                GalleryItem.editorial_state == "published",
            )
            .order_by(CollectionItem.position)
        ).all()
    )


def similarity_rows(session: Session, item_id: str, limit: int) -> list[SimilarityEdge]:
    return list(
        session.scalars(
            select(SimilarityEdge)
            .where(SimilarityEdge.item_id == item_id)
            .order_by(desc(SimilarityEdge.score))
            .limit(limit)
        ).all()
    )


def _vote_count(session: Session, kind: str, target_id: str) -> int:
    cached = session.get(VoteTotal, (kind, target_id))
    if cached is not None:
        return max(0, cached.count)
    return (
        session.scalar(
            select(func.count(ActiveVote.id)).where(
                ActiveVote.target_kind == kind, ActiveVote.target_id == target_id
            )
        )
        or 0
    )


def _has_voted(session: Session, actor_id: str | None, kind: str, target_id: str) -> bool:
    if not actor_id:
        return False
    return (
        session.scalar(
            select(ActiveVote.id).where(
                ActiveVote.actor_id == actor_id,
                ActiveVote.target_kind == kind,
                ActiveVote.target_id == target_id,
            )
        )
        is not None
    )


def _one_day():
    from datetime import timedelta

    return timedelta(days=1)


# Avoid a large dialect split while preserving JSON-list portability.
from sqlalchemy import String  # noqa: E402
