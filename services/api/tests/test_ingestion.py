from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import func, select

from romanpics_api.adapters import MastFixtureAdapter, StaticCatalogAdapter
from romanpics_api.models import ArchiveProduct, GalleryItem, Job, Rendition, Source, SourceRecord
from romanpics_api.services.ingestion import IngestionService


def test_mast_overwrite_keeps_item_id_and_release_supersedes(database, settings, tmp_path):
    _, factory = database
    fixtures = Path(__file__).parent / "fixtures"
    service = IngestionService(factory, settings.allowed_upstream_hosts)
    first = asyncio.run(
        service.sync(MastFixtureAdapter(fixtures / "mast-v1.json", enabled=True), full=True)
    )
    assert first.created_count == 1
    with factory() as session:
        original = session.scalar(select(GalleryItem))
        original_id = original.id
        prompt_record = session.scalar(select(SourceRecord))
        prompt_record_id = prompt_record.id

    overwritten = asyncio.run(
        service.sync(
            MastFixtureAdapter(fixtures / "mast-v1-overwrite.json", enabled=True), full=True
        )
    )
    assert overwritten.updated_count == 1
    with factory() as session:
        item = session.scalar(select(GalleryItem))
        assert item.id == original_id
        assert "reprocessed" in item.title.lower()
        assert session.scalar(select(func.count(SourceRecord.id))) == 1

    released = asyncio.run(
        service.sync(MastFixtureAdapter(fixtures / "mast-release-v2.json", enabled=True), full=True)
    )
    assert released.created_count == 1
    with factory() as session:
        prompt = session.get(SourceRecord, prompt_record_id)
        release = session.scalar(
            select(SourceRecord).where(SourceRecord.external_id.like("%release-v2"))
        )
        assert prompt.state == "superseded"
        assert prompt.superseded_by_id == release.id

    prompt_payload = json.loads((fixtures / "mast-v1-overwrite.json").read_text())
    release_payload = json.loads((fixtures / "mast-release-v2.json").read_text())
    combined = tmp_path / "mast-combined-reversed.json"
    combined.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "records": [release_payload["records"][0], prompt_payload["records"][0]],
            }
        )
    )
    asyncio.run(service.sync(MastFixtureAdapter(combined, enabled=True), full=True))
    with factory() as session:
        prompt = session.get(SourceRecord, prompt_record_id)
        assert prompt.state == "superseded"


def test_changed_record_reconciles_obsolete_products_and_renditions(
    database, settings, tmp_path
):
    _, factory = database
    payload = json.loads(
        (Path(__file__).parent / "fixtures" / "mast-v1.json").read_text()
    )
    initial = tmp_path / "initial-assets.json"
    initial.write_text(json.dumps(payload))
    service = IngestionService(factory, settings.allowed_upstream_hosts)
    asyncio.run(service.sync(MastFixtureAdapter(initial, enabled=True), full=True))

    old_product_url = payload["records"][0]["products"][0]["url"]
    old_rendition_url = payload["records"][0]["renditions"][0]["url"]
    new_product_url = old_product_url.replace("_coadd.asdf", "_coadd-v2.asdf")
    new_rendition_url = old_rendition_url.replace("_preview.jpg", "_preview-v2.jpg")
    payload["records"][0]["title"] += " reprocessed"
    payload["records"][0]["products"][0]["url"] = new_product_url
    payload["records"][0]["renditions"][0]["url"] = new_rendition_url
    updated = tmp_path / "updated-assets.json"
    updated.write_text(json.dumps(payload))
    asyncio.run(service.sync(MastFixtureAdapter(updated, enabled=True), full=True))

    with factory() as session:
        products = {
            row.external_url: row.active for row in session.scalars(select(ArchiveProduct))
        }
        rendition_urls = set(session.scalars(select(Rendition.url)))
        assert products[old_product_url] is False
        assert products[new_product_url] is True
        assert old_rendition_url not in rendition_urls
        assert new_rendition_url in rendition_urls


def test_full_reconciliation_only_after_nonempty_error_free_listing(database, settings, tmp_path):
    _, factory = database
    source_fixture = Path(__file__).parents[1] / "manifests" / "reviewed.json"
    payload = json.loads(source_fixture.read_text(encoding="utf-8"))
    service = IngestionService(factory, settings.allowed_upstream_hosts)

    initial_path = tmp_path / "initial.json"
    initial_path.write_text(json.dumps({**payload, "records": payload["records"][:2]}))
    asyncio.run(service.sync(StaticCatalogAdapter(initial_path), full=True))
    with factory() as session:
        source = session.scalar(select(Source))
        complete_at = source.last_complete_success_at
        assert (
            session.scalar(
                select(func.count(SourceRecord.id)).where(SourceRecord.state == "active")
            )
            == 2
        )

    partial_path = tmp_path / "partial.json"
    partial_path.write_text(
        json.dumps({**payload, "records": [payload["records"][0], {"external_id": "broken"}]})
    )
    partial = asyncio.run(service.sync(StaticCatalogAdapter(partial_path), full=True))
    assert partial.state == "partial"
    with factory() as session:
        source = session.scalar(select(Source))
        assert source.last_complete_success_at == complete_at
        assert (
            session.scalar(
                select(func.count(SourceRecord.id)).where(SourceRecord.state == "active")
            )
            == 2
        )

    empty = asyncio.run(
        service.sync(
            StaticCatalogAdapter(Path(__file__).parent / "fixtures" / "empty.json"), full=True
        )
    )
    assert empty.state == "partial"
    with factory() as session:
        assert (
            session.scalar(
                select(func.count(SourceRecord.id)).where(SourceRecord.state == "active")
            )
            == 2
        )

    complete_path = tmp_path / "complete.json"
    complete_path.write_text(json.dumps({**payload, "records": payload["records"][:1]}))
    completed = asyncio.run(service.sync(StaticCatalogAdapter(complete_path), full=True))
    assert completed.state == "succeeded"
    with factory() as session:
        assert (
            session.scalar(
                select(func.count(SourceRecord.id)).where(SourceRecord.state == "active")
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count(SourceRecord.id)).where(SourceRecord.state == "inactive")
            )
            == 1
        )


def test_incremental_sync_uses_48_hour_overlap(database, settings, tmp_path):
    _, factory = database
    source_fixture = Path(__file__).parents[1] / "manifests" / "reviewed.json"
    payload = json.loads(source_fixture.read_text(encoding="utf-8"))
    path = tmp_path / "one.json"
    path.write_text(json.dumps({**payload, "records": payload["records"][:1]}))
    service = IngestionService(factory, settings.allowed_upstream_hosts)
    asyncio.run(service.sync(StaticCatalogAdapter(path), full=True))

    class CapturingAdapter(StaticCatalogAdapter):
        captured = None

        async def discover(self, cursor=None, modified_since=None):
            self.captured = modified_since
            return await super().discover(cursor, modified_since)

    adapter = CapturingAdapter(path)
    asyncio.run(service.sync(adapter, full=False))
    with factory() as session:
        source = session.scalar(select(Source))
        delta = source.last_success_at - adapter.captured
        assert 47.9 * 3600 <= delta.total_seconds() <= 48.1 * 3600


def test_l3_without_preview_stays_draft_and_enqueues_bounded_render(database, settings):
    _, factory = database
    fixture = Path(__file__).parent / "fixtures" / "mast-l3-no-preview.json"
    run = asyncio.run(
        IngestionService(factory, settings.allowed_upstream_hosts).sync(
            MastFixtureAdapter(fixture, enabled=True), full=True
        )
    )
    assert run.created_count == 1
    with factory() as session:
        item = session.scalar(select(GalleryItem))
        render = session.scalar(select(Job).where(Job.job_type == "render"))
        assert item.editorial_state == "draft"
        assert item.metadata_json["publication_gate"] == "render"
        assert item.processing_note == "Awaiting a bounded site-generated preview."
        assert render.payload_json["item_id"] == item.id
        assert render.payload_json["recipe"]["version"] == "monochrome-v1"
        assert session.scalar(select(func.count(Job.id)).where(Job.job_type == "embed")) == 0
