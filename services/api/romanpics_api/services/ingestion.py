from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from ..adapters import NormalizedObservation, NormalizedRecord, SourceAdapter
from ..models import (
    ArchiveProduct,
    GalleryItem,
    IngestRun,
    ItemAsset,
    ItemTag,
    Observation,
    Rendition,
    RunState,
    Source,
    SourceRecord,
    Tag,
    stable_uuid,
    utcnow,
)
from .jobs import enqueue_cluster_refresh, enqueue_embed, enqueue_render
from .security import url_host_allowed


class IngestionService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        allowed_hosts: tuple[str, ...],
        *,
        max_pages: int = 25,
    ):
        self.session_factory = session_factory
        self.allowed_hosts = allowed_hosts
        self.max_pages = max_pages

    async def sync(self, adapter: SourceAdapter, *, full: bool = False) -> IngestRun:
        session = self.session_factory()
        source = session.scalar(select(Source).where(Source.adapter == adapter.name))
        if source is None:
            source = Source(
                id=stable_uuid("source", adapter.name),
                adapter=adapter.name,
                display_name=adapter.display_name,
                canonical_host=adapter.canonical_host,
                terms_url=adapter.terms_url,
            )
            session.add(source)
            session.flush()
        run = IngestRun(source_id=source.id)
        session.add(run)
        session.commit()
        run_id = run.id
        cursor = None if full else source.cursor
        modified_since = (
            None
            if full or not source.last_success_at
            else source.last_success_at - timedelta(hours=48)
        )
        errors: list[str] = []
        seen_external_ids: set[str] = set()
        listing_complete = False

        try:
            for _ in range(self.max_pages):
                page = await adapter.discover(cursor=cursor, modified_since=modified_since)
                run.discovered_count += len(page.records)
                session.commit()
                for raw in page.records:
                    try:
                        normalized = await adapter.normalize(raw)
                        seen_external_ids.add(normalized.external_id)
                        self._validate(normalized)
                        changed = self._upsert_record(session, source, normalized)
                        if changed == "created":
                            run.created_count += 1
                        elif changed == "updated":
                            run.updated_count += 1
                        else:
                            run.unchanged_count += 1
                        session.commit()
                    except Exception as exc:  # isolate malformed upstream records
                        session.rollback()
                        run = session.get(IngestRun, run_id)
                        run.failed_count += 1
                        external = raw.get("id") or raw.get("external_id") or raw.get("data")
                        errors.append(f"{str(external)[:120]}: {exc}")
                        session.commit()
                cursor = page.next_cursor
                source = session.get(Source, source.id)
                source.cursor = cursor
                run = session.get(IngestRun, run_id)
                run.next_cursor = cursor
                session.commit()
                if cursor is None:
                    listing_complete = True
                    break
            else:
                errors.append(f"stopped at configured max_pages={self.max_pages}")

            if full and listing_complete and not seen_external_ids:
                errors.append("full listing was empty; skipped destructive reconciliation")
            if full and listing_complete and seen_external_ids and not errors:
                self._reconcile_missing(session, source.id, seen_external_ids)
            self._reapply_supersessions(session, source.id)

            run = session.get(IngestRun, run_id)
            source = session.get(Source, source.id)
            run.state = RunState.PARTIAL.value if errors else RunState.SUCCEEDED.value
            run.finished_at = utcnow()
            run.error_summary = "\n".join(errors[:20]) or None
            source.last_success_at = utcnow()
            if full and listing_complete and seen_external_ids and not errors:
                source.last_complete_success_at = utcnow()
            if errors:
                source.last_error_at = utcnow()
                source.last_error = run.error_summary
            else:
                source.last_error = None
            if run.created_count + run.updated_count > 0:
                enqueue_cluster_refresh(session, source_id=source.id, ingest_run_id=run.id)
            session.commit()
            session.refresh(run)
            return run
        except Exception as exc:
            session.rollback()
            run = session.get(IngestRun, run_id)
            source = session.get(Source, run.source_id)
            run.state = RunState.FAILED.value
            run.finished_at = utcnow()
            run.error_summary = str(exc)[:4_000]
            source.last_error_at = utcnow()
            source.last_error = str(exc)[:4_000]
            session.commit()
            raise
        finally:
            session.close()

    def _validate(self, record: NormalizedRecord) -> None:
        if record.content_class not in {
            "FLIGHT_SCIENCE",
            "SIMULATION",
            "GROUND_TEST",
            "MISSION_PHOTO",
            "VISUALIZATION",
        }:
            raise ValueError(f"invalid content class: {record.content_class}")
        if record.is_flight_data != (record.content_class == "FLIGHT_SCIENCE"):
            raise ValueError("is_flight_data must exactly match FLIGHT_SCIENCE")
        urls = [record.canonical_url]
        urls.extend(product.url for product in record.products)
        urls.extend(rendition.url for rendition in record.renditions)
        rejected = [url for url in urls if not url_host_allowed(url, self.allowed_hosts)]
        if rejected:
            raise ValueError(f"URL host is not allowlisted: {rejected[0]}")
        if not record.renditions and self._renderable_product(record) is None:
            raise ValueError("a browser rendition or renderable L3 product is required")
        if not record.credit.strip() or not record.alt_text.strip():
            raise ValueError("credit and alt text are required")

    def _upsert_record(self, session: Session, source: Source, normalized: NormalizedRecord) -> str:
        checksum = _checksum(normalized)
        source_record = session.scalar(
            select(SourceRecord).where(
                SourceRecord.source_id == source.id,
                SourceRecord.external_id == normalized.external_id,
            )
        )
        outcome = "created"
        if source_record is None:
            source_record = SourceRecord(
                id=stable_uuid("source-record", f"{source.adapter}:{normalized.external_id}"),
                source_id=source.id,
                external_id=normalized.external_id,
                canonical_url=normalized.canonical_url,
                checksum=checksum,
                raw_metadata=normalized.raw,
            )
            session.add(source_record)
            session.flush()
        elif source_record.checksum == checksum and source_record.state == "active":
            source_record.supersedes_external_id = normalized.supersedes_external_id
            return "unchanged"
        else:
            outcome = "updated"
        source_record.canonical_url = normalized.canonical_url
        source_record.upstream_created_at = normalized.upstream_created_at
        source_record.upstream_updated_at = normalized.upstream_updated_at
        source_record.etag = normalized.etag
        source_record.checksum = checksum
        source_record.raw_metadata = normalized.raw
        source_record.state = "active"
        source_record.supersedes_external_id = normalized.supersedes_external_id

        if normalized.supersedes_external_id:
            predecessor = session.scalar(
                select(SourceRecord).where(
                    SourceRecord.source_id == source.id,
                    SourceRecord.external_id == normalized.supersedes_external_id,
                )
            )
            if predecessor is not None and predecessor.id != source_record.id:
                predecessor.state = "superseded"
                predecessor.superseded_by_id = source_record.id
                for product in session.scalars(
                    select(ArchiveProduct).where(ArchiveProduct.source_record_id == predecessor.id)
                ):
                    product.active = False

        observation = self._upsert_observation(session, normalized.observation)
        item = session.scalar(
            select(GalleryItem).where(GalleryItem.primary_source_record_id == source_record.id)
        )
        if item is None:
            item = GalleryItem(
                id=stable_uuid("gallery-item", f"{source.adapter}:{normalized.external_id}"),
                primary_source_record_id=source_record.id,
                slug=self._available_slug(session, normalized.slug, normalized.external_id),
                title=normalized.title,
                plain_summary=normalized.summary,
                content_class=normalized.content_class,
                is_flight_data=normalized.is_flight_data,
                alt_text=normalized.alt_text,
            )
            session.add(item)
            session.flush()
        was_awaiting_render = item.processing_note == "Awaiting a bounded site-generated preview."
        item.title = normalized.title
        item.plain_summary = normalized.summary
        item.content_class = normalized.content_class
        item.is_flight_data = normalized.is_flight_data
        item.primary_observation_id = observation.id if observation else None
        item.published_at = normalized.published_at
        item.alt_text = normalized.alt_text
        item.processing_note = normalized.processing_note
        item.metadata_json = normalized.metadata
        item.search_document = " ".join(
            [
                normalized.title,
                normalized.summary,
                normalized.credit,
                *(normalized.tags or []),
                normalized.observation.target
                if normalized.observation and normalized.observation.target
                else "",
            ]
        ).lower()

        products: list[ArchiveProduct] = []
        current_product_urls = {product.url for product in normalized.products}
        for existing_product in session.scalars(
            select(ArchiveProduct).where(ArchiveProduct.source_record_id == source_record.id)
        ):
            if existing_product.external_url not in current_product_urls:
                existing_product.active = False
        for product in normalized.products:
            row = session.scalar(
                select(ArchiveProduct).where(
                    ArchiveProduct.source_record_id == source_record.id,
                    ArchiveProduct.external_url == product.url,
                )
            )
            if row is None:
                row = ArchiveProduct(
                    id=stable_uuid(
                        "archive-product",
                        f"{source.adapter}:{normalized.external_id}:{product.url}",
                    ),
                    source_record_id=source_record.id,
                    external_url=product.url,
                    media_type=product.media_type,
                    subtype=product.subtype,
                )
                session.add(row)
            row.observation_id = observation.id if observation else None
            row.media_type = product.media_type
            row.subtype = product.subtype
            row.data_level = product.data_level or (observation.data_level if observation else None)
            row.byte_size = product.byte_size
            row.is_original = product.is_original
            row.active = True
            products.append(row)
        session.flush()
        for position, product in enumerate(products):
            link = session.get(ItemAsset, (item.id, product.id))
            if link is None:
                session.add(
                    ItemAsset(
                        item_id=item.id,
                        product_id=product.id,
                        role="original" if product.is_original else "product",
                        position=position,
                    )
                )

        if not normalized.renditions:
            render_product = self._renderable_product(normalized)
            if render_product is None:
                raise RuntimeError("validated renderable record lost its source product")
            product_index = normalized.products.index(render_product)
            item.editorial_state = "draft"
            item.processing_note = "Awaiting a bounded site-generated preview."
            item.metadata_json = {**item.metadata_json, "publication_gate": "render"}
            enqueue_render(
                session,
                item_id=item.id,
                product_id=products[product_index].id,
                recipe={"version": "monochrome-v1", "array_key": None},
                source_checksum=checksum,
            )
        elif was_awaiting_render and item.editorial_state == "draft":
            item.editorial_state = "published"
            item.metadata_json = {
                key: value for key, value in item.metadata_json.items() if key != "publication_gate"
            }

        current_rendition_urls = {rendition.url for rendition in normalized.renditions}
        if normalized.renditions:
            session.execute(
                delete(Rendition).where(
                    Rendition.item_id == item.id,
                    Rendition.url.not_in(current_rendition_urls),
                )
            )
        else:
            session.execute(
                delete(Rendition).where(
                    Rendition.item_id == item.id,
                    Rendition.is_site_derivative.is_(False),
                    Rendition.url.not_in(current_rendition_urls),
                )
            )

        for rendition in normalized.renditions:
            row = session.scalar(
                select(Rendition).where(
                    Rendition.item_id == item.id, Rendition.url == rendition.url
                )
            )
            if row is None:
                row = Rendition(item_id=item.id, url=rendition.url)
                row.id = stable_uuid("rendition", f"{item.id}:{rendition.url}")
                session.add(row)
            row.provider = rendition.provider
            row.width = rendition.width
            row.height = rendition.height
            row.format = rendition.format
            row.is_site_derivative = rendition.site_generated
            row.recipe = rendition.transformation
            row.alt_text = rendition.alt_text
            row.credit = rendition.credit
            row.rights = rendition.rights
            row.rights_url = rendition.rights_url
            row.role = rendition.role

        session.execute(ItemTag.__table__.delete().where(ItemTag.item_id == item.id))
        for label in dict.fromkeys(tag.strip() for tag in normalized.tags if tag.strip()):
            slug = _tag_slug(label)
            tag = session.scalar(select(Tag).where(Tag.slug == slug))
            if tag is None:
                tag = Tag(slug=slug, label=label, aliases=[])
                tag.id = stable_uuid("tag", slug)
                session.add(tag)
                session.flush()
            session.add(ItemTag(item_id=item.id, tag_id=tag.id))
        if normalized.renditions:
            enqueue_embed(
                session,
                item_id=item.id,
                source_record_id=source_record.id,
                checksum=checksum,
            )
        return outcome

    @staticmethod
    def _renderable_product(record: NormalizedRecord):
        """Choose only an L3 image product; raw L1/L2 detector files stay upstream."""
        for product in record.products:
            level = (product.data_level or "").upper()
            media_type = product.media_type.lower()
            if level.startswith("L3") and media_type in {
                "application/fits",
                "application/x-fits",
                "application/asdf",
                "application/x-asdf",
            }:
                return product
        return None

    @staticmethod
    def _upsert_observation(
        session: Session, value: NormalizedObservation | None
    ) -> Observation | None:
        if value is None:
            return None
        row = session.scalar(
            select(Observation).where(
                Observation.mission == value.mission,
                Observation.observation_id == value.observation_id,
            )
        )
        if row is None:
            row = Observation(mission=value.mission, observation_id=value.observation_id)
            row.id = stable_uuid("observation", f"{value.mission}:{value.observation_id}")
            session.add(row)
        row.program_id = value.program_id
        row.survey = value.survey
        row.instrument = value.instrument
        row.mode = value.mode
        row.optical_elements = value.optical_elements
        row.target_name = value.target
        row.ra = value.ra
        row.dec = value.dec
        row.observed_start = value.observed_start
        row.observed_end = value.observed_end
        row.data_level = value.data_level
        row.product_version = value.product_version
        row.pipeline_version = value.pipeline_version
        row.release_name = value.release_name
        session.flush()
        return row

    @staticmethod
    def _available_slug(session: Session, proposed: str, external_id: str) -> str:
        slug = proposed[:240].strip("-") or "untitled"
        if session.scalar(select(GalleryItem.id).where(GalleryItem.slug == slug)) is None:
            return slug
        suffix = (
            _tag_slug(external_id)[-32:] or hashlib.sha256(external_id.encode()).hexdigest()[:8]
        )
        return f"{slug[: 240 - len(suffix) - 1]}-{suffix}"

    @staticmethod
    def _reconcile_missing(session: Session, source_id: str, seen_external_ids: set[str]) -> None:
        missing = session.scalars(
            select(SourceRecord).where(
                SourceRecord.source_id == source_id,
                SourceRecord.state == "active",
                SourceRecord.external_id.not_in(seen_external_ids),
            )
        ).all()
        for record in missing:
            record.state = "inactive"
            for product in session.scalars(
                select(ArchiveProduct).where(ArchiveProduct.source_record_id == record.id)
            ):
                product.active = False

    @staticmethod
    def _reapply_supersessions(session: Session, source_id: str) -> None:
        superseders = session.scalars(
            select(SourceRecord).where(
                SourceRecord.source_id == source_id,
                SourceRecord.state == "active",
                SourceRecord.supersedes_external_id.is_not(None),
            )
        ).all()
        for superseder in superseders:
            predecessor = session.scalar(
                select(SourceRecord).where(
                    SourceRecord.source_id == source_id,
                    SourceRecord.external_id == superseder.supersedes_external_id,
                )
            )
            if predecessor is None or predecessor.id == superseder.id:
                continue
            predecessor.state = "superseded"
            predecessor.superseded_by_id = superseder.id
            for product in session.scalars(
                select(ArchiveProduct).where(ArchiveProduct.source_record_id == predecessor.id)
            ):
                product.active = False


def source_status(session: Session) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    rows = []
    for source in session.scalars(select(Source).order_by(Source.display_name)).all():
        record_count = (
            session.scalar(
                select(func.count(SourceRecord.id)).where(
                    SourceRecord.source_id == source.id, SourceRecord.state == "active"
                )
            )
            or 0
        )
        delayed = source.last_success_at is None or now - _aware(
            source.last_success_at
        ) > timedelta(seconds=source.poll_interval_seconds * 2)
        state = "degraded" if source.last_error else "delayed" if delayed else "healthy"
        rows.append(
            {
                "adapter": source.adapter,
                "state": state,
                "last_success_at": source.last_success_at,
                "last_error_at": source.last_error_at,
                "public_message": "An upstream synchronization reported errors. Existing records remain available."
                if source.last_error
                else None,
                "record_count": record_count,
            }
        )
    return rows


def _checksum(record: NormalizedRecord) -> str:
    payload = json.dumps(
        dataclasses.asdict(record), sort_keys=True, default=str, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _tag_slug(value: str) -> str:
    return "-".join("".join(char.lower() if char.isalnum() else " " for char in value).split())[
        :100
    ]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
