from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import func, select

from romanpics_api.models import (
    ArchiveProduct,
    Cluster,
    ClusterMember,
    Collection,
    GalleryItem,
    Job,
    Rendition,
    SimilarityEdge,
    SourceRecord,
)
from romanpics_api.services.seed import seed_catalog


def test_seed_replay_is_idempotent_and_ids_are_deterministic(database, settings):
    _, factory = database
    path = Path(__file__).parents[1] / "manifests" / "reviewed.json"
    first = asyncio.run(seed_catalog(factory, path, settings.allowed_upstream_hosts))
    with factory() as session:
        ids_before = dict(session.execute(select(GalleryItem.slug, GalleryItem.id)).all())
    second = asyncio.run(seed_catalog(factory, path, settings.allowed_upstream_hosts))
    with factory() as session:
        ids_after = dict(session.execute(select(GalleryItem.slug, GalleryItem.id)).all())
        assert session.scalar(select(func.count(GalleryItem.id))) == 8
        assert session.scalar(select(func.count(SourceRecord.id))) == 8
        assert session.scalar(select(func.count(Cluster.id))) == 3
        assert session.scalar(select(func.count(Collection.id))) == 3
        assert session.scalar(select(func.count(Job.id))) == 9
    assert ids_before == ids_after
    assert ids_before["launch-day"] == "4c263736-41ed-5918-abac-8edf0bd38db8"
    assert first["items"] == second["items"] == 8


def test_seed_replay_never_replaces_a_computed_similarity_graph(database, settings):
    _, factory = database
    path = Path(__file__).parents[1] / "manifests" / "reviewed.json"
    asyncio.run(seed_catalog(factory, path, settings.allowed_upstream_hosts))
    with factory() as session:
        members = list(session.scalars(select(GalleryItem).order_by(GalleryItem.id).limit(2)))
        session.query(ClusterMember).delete()
        session.query(Cluster).delete()
        session.query(SimilarityEdge).delete()
        cluster = Cluster(
            id="11111111-1111-4111-8111-111111111111",
            slug="computed-group",
            title="Computed group",
            summary="A worker-owned graph snapshot.",
            content_class=members[0].content_class,
            algorithm_version="cosine-knn-components-v1",
            representative_item_id=members[0].id,
        )
        session.add(cluster)
        session.add(
            ClusterMember(cluster_id=cluster.id, item_id=members[0].id, similarity=1.0, rank=0)
        )
        session.add(
            SimilarityEdge(
                id="22222222-2222-4222-8222-222222222222",
                item_id=members[0].id,
                related_item_id=members[1].id,
                score=0.91,
                reasons=["cosine"],
                algorithm_version="cosine-knn-components-v1",
            )
        )
        session.commit()

    replay = asyncio.run(seed_catalog(factory, path, settings.allowed_upstream_hosts))
    with factory() as session:
        assert session.scalar(select(func.count(Cluster.id))) == 1
        assert session.scalar(select(Cluster.slug)) == "computed-group"
        assert session.scalar(select(func.count(SimilarityEdge.id))) == 1
        assert session.scalar(select(SimilarityEdge.algorithm_version)) == (
            "cosine-knn-components-v1"
        )
    assert replay["clusters"] == 0
    assert replay["similarities"] == 0


def test_camel_case_shared_catalog_loader(database, settings, tmp_path):
    _, factory = database
    payload = {
        "items": [
            {
                "id": "shared-one",
                "title": "Shared catalog item",
                "contentClass": "Simulations",
                "detail": "A clearly labeled synthetic view.",
                "image": "https://svs.gsfc.nasa.gov/vis/example_searchweb.jpg",
                "href": "https://svs.gsfc.nasa.gov/99999/",
                "credit": "NASA GSFC",
                "alt": "A synthetic star field.",
                "tags": ["simulation"],
                "votes": 12,
            }
        ],
        "groups": [],
    }
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = asyncio.run(seed_catalog(factory, path, settings.allowed_upstream_hosts))
    assert result["items"] == 1
    with factory() as session:
        item = session.scalar(select(GalleryItem).where(GalleryItem.slug == "shared-one"))
        assert item.content_class == "SIMULATION"
        assert item.metadata_json["legacy_vote_hint"] == 12


def test_real_shared_catalog_preserves_classes_previews_and_originals(database, settings):
    _, factory = database
    path = Path(__file__).parents[3] / "data" / "catalog.json"
    result = asyncio.run(seed_catalog(factory, path, settings.allowed_upstream_hosts))
    assert result["items"] == 8
    assert result["clusters"] == 3
    assert result["collections"] == 5
    assert result["similarities"] == 8
    with factory() as session:
        launch = session.scalar(select(GalleryItem).where(GalleryItem.slug == "launch-day"))
        cleanroom = session.scalar(
            select(GalleryItem).where(GalleryItem.slug == "cleanroom-at-work")
        )
        assert launch.content_class == "MISSION_PHOTO"
        assert cleanroom.content_class == "GROUND_TEST"
        preview = session.scalar(select(Rendition).where(Rendition.item_id == cleanroom.id))
        assert preview.url.endswith("_searchweb.png")
        products = list(
            session.scalars(
                select(ArchiveProduct).where(
                    ArchiveProduct.source_record_id == launch.primary_source_record_id
                )
            )
        )
        assert any(
            product.is_original and product.external_url.endswith("~orig.jpg")
            for product in products
        )
        assert any(product.media_type == "text/html" for product in products)
