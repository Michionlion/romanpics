from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_uuid() -> str:
    return str(uuid.uuid4())


ROMANPICS_NAMESPACE = uuid.UUID("65b45bda-080e-53bb-a019-17641a1939ac")


def stable_uuid(kind: str, key: str) -> str:
    """Return a durable public ID for reconstructable catalog entities."""
    return str(uuid.uuid5(ROMANPICS_NAMESPACE, f"{kind}:{key}"))


class ContentClass(StrEnum):
    FLIGHT_SCIENCE = "FLIGHT_SCIENCE"
    SIMULATION = "SIMULATION"
    GROUND_TEST = "GROUND_TEST"
    MISSION_PHOTO = "MISSION_PHOTO"
    VISUALIZATION = "VISUALIZATION"


class EditorialState(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    HIDDEN = "hidden"


class RunState(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Source(Base, TimestampMixin):
    __tablename__ = "source"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    adapter: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical_host: Mapped[str] = mapped_column(String(255), nullable=False)
    terms_url: Mapped[str | None] = mapped_column(Text)
    cursor: Mapped[str | None] = mapped_column(Text)
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=86_400)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_complete_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class SourceRecord(Base, TimestampMixin):
    __tablename__ = "source_record"
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    upstream_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    upstream_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    etag: Mapped[str | None] = mapped_column(String(255))
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_metadata: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(32), default="active")
    supersedes_external_id: Mapped[str | None] = mapped_column(String(512), index=True)
    superseded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_record.id", ondelete="SET NULL")
    )


class Observation(Base, TimestampMixin):
    __tablename__ = "observation"
    __table_args__ = (UniqueConstraint("mission", "observation_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    mission: Mapped[str] = mapped_column(String(64), default="Roman")
    observation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    program_id: Mapped[str | None] = mapped_column(String(255))
    survey: Mapped[str | None] = mapped_column(String(255), index=True)
    instrument: Mapped[str | None] = mapped_column(String(100), index=True)
    mode: Mapped[str | None] = mapped_column(String(100))
    optical_elements: Mapped[list[str]] = mapped_column(JSON, default=list)
    target_name: Mapped[str | None] = mapped_column(String(255), index=True)
    ra: Mapped[float | None] = mapped_column(Float)
    dec: Mapped[float | None] = mapped_column(Float)
    healpix: Mapped[int | None] = mapped_column(Integer, index=True)
    footprint: Mapped[dict[str, object] | None] = mapped_column(JSON)
    observed_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_level: Mapped[str | None] = mapped_column(String(32))
    product_version: Mapped[str | None] = mapped_column(String(100))
    pipeline_version: Mapped[str | None] = mapped_column(String(100))
    release_name: Mapped[str | None] = mapped_column(String(255))


class ArchiveProduct(Base, TimestampMixin):
    __tablename__ = "archive_product"
    __table_args__ = (UniqueConstraint("source_record_id", "external_url"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    observation_id: Mapped[str | None] = mapped_column(
        ForeignKey("observation.id", ondelete="SET NULL"), index=True
    )
    source_record_id: Mapped[str] = mapped_column(
        ForeignKey("source_record.id", ondelete="CASCADE"), index=True
    )
    external_url: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int | None] = mapped_column(Integer)
    subtype: Mapped[str] = mapped_column(String(100), nullable=False)
    data_level: Mapped[str | None] = mapped_column(String(32))
    is_original: Mapped[bool] = mapped_column(Boolean, default=False)
    derived_from_id: Mapped[str | None] = mapped_column(
        ForeignKey("archive_product.id", ondelete="SET NULL")
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    superseded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("archive_product.id", ondelete="SET NULL")
    )


class GalleryItem(Base, TimestampMixin):
    __tablename__ = "gallery_item"
    __table_args__ = (
        CheckConstraint(
            "content_class in ('FLIGHT_SCIENCE','SIMULATION','GROUND_TEST','MISSION_PHOTO','VISUALIZATION')",
            name="ck_gallery_item_content_class",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    plain_summary: Mapped[str] = mapped_column(Text, nullable=False)
    content_class: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    is_flight_data: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    primary_source_record_id: Mapped[str] = mapped_column(
        ForeignKey("source_record.id", ondelete="RESTRICT"), unique=True, index=True
    )
    primary_observation_id: Mapped[str | None] = mapped_column(
        ForeignKey("observation.id", ondelete="SET NULL"), index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    editorial_state: Mapped[str] = mapped_column(
        String(32), default=EditorialState.PUBLISHED.value, index=True
    )
    alt_text: Mapped[str] = mapped_column(Text, nullable=False)
    processing_note: Mapped[str | None] = mapped_column(Text)
    search_document: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class ItemAsset(Base):
    __tablename__ = "item_asset"

    item_id: Mapped[str] = mapped_column(
        ForeignKey("gallery_item.id", ondelete="CASCADE"), primary_key=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("archive_product.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(50), default="original")
    position: Mapped[int] = mapped_column(Integer, default=0)


class Rendition(Base, TimestampMixin):
    __tablename__ = "rendition"
    __table_args__ = (UniqueConstraint("item_id", "url"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    item_id: Mapped[str] = mapped_column(
        ForeignKey("gallery_item.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    format: Mapped[str] = mapped_column(String(100), nullable=False)
    is_site_derivative: Mapped[bool] = mapped_column(Boolean, default=False)
    recipe: Mapped[str | None] = mapped_column(Text)
    alt_text: Mapped[str] = mapped_column(Text, nullable=False)
    credit: Mapped[str] = mapped_column(Text, nullable=False)
    rights: Mapped[str | None] = mapped_column(Text)
    rights_url: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(50), default="preview", index=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Tag(Base):
    __tablename__ = "tag"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)


class ItemTag(Base):
    __tablename__ = "item_tag"

    item_id: Mapped[str] = mapped_column(
        ForeignKey("gallery_item.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[str] = mapped_column(ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True)


class Embedding(Base, TimestampMixin):
    __tablename__ = "embedding"
    __table_args__ = (UniqueConstraint("item_id", "model", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    item_id: Mapped[str] = mapped_column(
        ForeignKey("gallery_item.id", ondelete="CASCADE"), index=True
    )
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    vector: Mapped[list[float] | None] = mapped_column(JSON)
    perceptual_hash: Mapped[str | None] = mapped_column(String(128), index=True)


class Cluster(Base, TimestampMixin):
    __tablename__ = "cluster"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    content_class: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    algorithm_version: Mapped[str] = mapped_column(String(100), nullable=False)
    representative_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("gallery_item.id", ondelete="SET NULL")
    )
    centroid: Mapped[list[float] | None] = mapped_column(JSON)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClusterMember(Base):
    __tablename__ = "cluster_member"

    cluster_id: Mapped[str] = mapped_column(
        ForeignKey("cluster.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[str] = mapped_column(
        ForeignKey("gallery_item.id", ondelete="CASCADE"), primary_key=True
    )
    similarity: Mapped[float] = mapped_column(Float, default=1.0)
    rank: Mapped[int] = mapped_column(Integer, default=0)


class SimilarityEdge(Base):
    __tablename__ = "similarity_edge"
    __table_args__ = (
        UniqueConstraint("item_id", "related_item_id", "algorithm_version"),
        CheckConstraint("item_id <> related_item_id", name="ck_similarity_no_self"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    item_id: Mapped[str] = mapped_column(
        ForeignKey("gallery_item.id", ondelete="CASCADE"), index=True
    )
    related_item_id: Mapped[str] = mapped_column(
        ForeignKey("gallery_item.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    algorithm_version: Mapped[str] = mapped_column(String(100), nullable=False)


class Collection(Base, TimestampMixin):
    __tablename__ = "collection"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    published: Mapped[bool] = mapped_column(Boolean, default=True)


class CollectionItem(Base):
    __tablename__ = "collection_item"

    collection_id: Mapped[str] = mapped_column(
        ForeignKey("collection.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[str] = mapped_column(
        ForeignKey("gallery_item.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text)


class VoteEvent(Base):
    __tablename__ = "vote_event"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    target_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    network_hmac: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ActiveVote(Base):
    __tablename__ = "active_vote"
    __table_args__ = (
        UniqueConstraint("actor_id", "target_kind", "target_id"),
        Index("ix_active_vote_target", "target_kind", "target_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    target_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VoteTotal(Base):
    __tablename__ = "vote_total"

    target_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    target_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class IngestRun(Base):
    __tablename__ = "ingest_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id", ondelete="CASCADE"), index=True)
    state: Mapped[str] = mapped_column(String(32), default=RunState.RUNNING.value)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discovered_count: Mapped[int] = mapped_column(Integer, default=0)
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text)
    next_cursor: Mapped[str | None] = mapped_column(Text)


class LinkCheck(Base):
    __tablename__ = "link_check"
    __table_args__ = (Index("ix_link_check_url_checked", "url", "checked_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    target_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    final_url: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base, TimestampMixin):
    """PostgreSQL-friendly worker lease queue; SQLite remains test-compatible."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "status in ('queued','running','succeeded','failed','cancelled')",
            name="ck_jobs_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_jobs_attempts_nonnegative"),
        CheckConstraint("max_attempts > 0", name="ck_jobs_max_attempts_positive"),
        Index("ix_jobs_claim", "status", "available_at", "priority"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    locked_by: Mapped[str | None] = mapped_column(String(255), index=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dedupe_key: Mapped[str | None] = mapped_column(String(512), unique=True)
    result_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
