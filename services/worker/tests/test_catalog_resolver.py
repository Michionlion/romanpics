from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from romanpics_worker.catalog import SqliteCatalogResolver

ITEM_ID = "11111111-1111-4111-8111-111111111111"
PRODUCT_ID = "22222222-2222-4222-8222-222222222222"
RECORD_ID = "33333333-3333-4333-8333-333333333333"
SOURCE_ID = "44444444-4444-4444-8444-444444444444"
RUN_ID = "55555555-5555-4555-8555-555555555555"
CHECKSUM = "a" * 64


def database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE source_record (
            id TEXT PRIMARY KEY, source_id TEXT, canonical_url TEXT,
            checksum TEXT, state TEXT, raw_metadata TEXT
        );
        CREATE TABLE gallery_item (
            id TEXT PRIMARY KEY, title TEXT, plain_summary TEXT, content_class TEXT,
            metadata_json TEXT, primary_observation_id TEXT, primary_source_record_id TEXT,
            editorial_state TEXT, processing_note TEXT, alt_text TEXT, updated_at TEXT
        );
        CREATE TABLE archive_product (
            id TEXT PRIMARY KEY, source_record_id TEXT, external_url TEXT,
            media_type TEXT, active INTEGER
        );
        CREATE TABLE item_asset (item_id TEXT, product_id TEXT);
        CREATE TABLE rendition (
            id TEXT PRIMARY KEY, item_id TEXT, provider TEXT, url TEXT, width INTEGER,
            height INTEGER, format TEXT, is_site_derivative INTEGER, recipe TEXT,
            alt_text TEXT, credit TEXT, rights TEXT, rights_url TEXT, role TEXT,
            last_verified_at TEXT, created_at TEXT, updated_at TEXT,
            UNIQUE (item_id, url)
        );
        CREATE TABLE ingest_run (id TEXT PRIMARY KEY, source_id TEXT);
        CREATE TABLE embedding (
            id TEXT PRIMARY KEY, item_id TEXT, model TEXT, version TEXT, vector TEXT,
            perceptual_hash TEXT, created_at TEXT, updated_at TEXT,
            UNIQUE (item_id, model, version)
        );
        CREATE TABLE cluster (
            id TEXT PRIMARY KEY, slug TEXT UNIQUE, title TEXT, summary TEXT,
            content_class TEXT, algorithm_version TEXT, representative_item_id TEXT,
            centroid TEXT, archived_at TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE cluster_member (
            cluster_id TEXT, item_id TEXT, similarity REAL, rank INTEGER,
            PRIMARY KEY (cluster_id, item_id)
        );
        CREATE TABLE similarity_edge (
            id TEXT PRIMARY KEY, item_id TEXT, related_item_id TEXT, score REAL,
            reasons TEXT, algorithm_version TEXT,
            UNIQUE (item_id, related_item_id, algorithm_version)
        );
        CREATE TABLE link_check (
            id TEXT PRIMARY KEY, url TEXT, target_kind TEXT, target_id TEXT,
            ok INTEGER, status_code INTEGER, final_url TEXT, error TEXT, checked_at TEXT
        );
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY, job_type TEXT, payload_json TEXT, status TEXT,
            priority INTEGER, attempts INTEGER, max_attempts INTEGER,
            available_at TEXT, locked_by TEXT, locked_at TEXT, dedupe_key TEXT UNIQUE,
            result_json TEXT, error TEXT, created_at TEXT, updated_at TEXT
        );
        """
    )
    connection.execute(
        "INSERT INTO source_record VALUES (?, ?, ?, ?, 'active', ?)",
        (
            RECORD_ID,
            SOURCE_ID,
            "https://archive.example.org/record",
            CHECKSUM,
            json.dumps({"credit": "NASA/STScI", "rights": "Public domain"}),
        ),
    )
    connection.execute(
        """INSERT INTO gallery_item VALUES (
               ?, 'Field', 'Summary', 'SIMULATION', ?, ?, ?,
               'draft', ?, 'A synthetic Roman field', ?
           )""",
        (
            ITEM_ID,
            json.dumps({"survey": "demo", "publication_gate": "render"}),
            "observation-1",
            RECORD_ID,
            "Awaiting a bounded site-generated preview.",
            "2026-08-30 00:00:00",
        ),
    )
    connection.execute(
        "INSERT INTO archive_product VALUES (?, ?, ?, 'application/fits', 1)",
        (PRODUCT_ID, RECORD_ID, "https://archive.example.org/product.fits"),
    )
    connection.execute("INSERT INTO item_asset VALUES (?, ?)", (ITEM_ID, PRODUCT_ID))
    connection.execute(
        """INSERT INTO rendition VALUES (
               'rendition-1', ?, 'upstream', ?, 100, 100, 'png', 0, NULL,
               'Alt', 'NASA', NULL, NULL, 'preview', NULL, ?, ?
           )""",
        (
            ITEM_ID,
            "https://archive.example.org/preview.png",
            "2026-08-30 00:00:00",
            "2026-08-30 00:00:00",
        ),
    )
    connection.execute("INSERT INTO ingest_run VALUES (?, ?)", (RUN_ID, SOURCE_ID))
    connection.execute(
        "INSERT INTO embedding VALUES ('old-embedding', ?, 'old', 'v1', ?, NULL, ?, ?)",
        (
            ITEM_ID,
            json.dumps([1.0, 0.0]),
            "2026-08-30 00:00:00",
            "2026-08-30 00:00:00",
        ),
    )
    connection.commit()
    connection.close()


def test_resolver_derives_urls_from_related_catalog_rows_and_checks_checksum(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    database(path)
    resolver = SqliteCatalogResolver(path)

    rendered = resolver.resolve_render(
        {"item_id": ITEM_ID, "product_id": PRODUCT_ID, "recipe": {"version": "v1"}}
    )
    assert rendered.source_url == "https://archive.example.org/product.fits"
    embedded = resolver.resolve_embed(
        {"item_id": ITEM_ID, "source_record_id": RECORD_ID, "checksum": CHECKSUM}
    )
    assert embedded.image_url == "https://archive.example.org/preview.png"
    assert embedded.metadata["survey"] == "demo"
    assert embedded.metadata["content_class"] == "SIMULATION"
    assert embedded.site_generated is False

    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE gallery_item SET editorial_state = 'published' WHERE id = ?", (ITEM_ID,)
    )
    connection.commit()
    connection.close()

    clustered = resolver.resolve_cluster({"source_id": SOURCE_ID, "ingest_run_id": RUN_ID})
    assert len(clustered.items) == 1
    assert clustered.eligible_item_count == 1
    assert clustered.items[0].family_keys == frozenset({"observation:observation-1"})

    links = resolver.resolve_link_targets({"scope": "catalog"})
    assert {target.url for target in links} == {
        "https://archive.example.org/record",
        "https://archive.example.org/product.fits",
        "https://archive.example.org/preview.png",
    }


def test_resolver_rejects_unrelated_product_stale_checksum_and_arbitrary_scope(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    database(path)
    resolver = SqliteCatalogResolver(path)
    connection = sqlite3.connect(path)
    connection.execute(
        "INSERT INTO archive_product VALUES ('other-product', ?, ?, 'application/fits', 1)",
        (RECORD_ID, "https://evil.invalid/not-associated.fits"),
    )
    connection.commit()
    connection.close()

    try:
        resolver.resolve_render({"item_id": ITEM_ID, "product_id": "other-product", "recipe": {}})
    except LookupError:
        pass
    else:
        raise AssertionError("unrelated product should not resolve")

    try:
        resolver.resolve_embed(
            {"item_id": ITEM_ID, "source_record_id": RECORD_ID, "checksum": "b" * 64}
        )
    except LookupError:
        pass
    else:
        raise AssertionError("stale checksum should not resolve")

    try:
        resolver.resolve_link_targets({"scope": "https://evil.invalid"})
    except ValueError:
        pass
    else:
        raise AssertionError("arbitrary link-check scope should not resolve")


def test_cluster_trigger_recomputes_across_active_sources(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    database(path)
    other_source = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    other_record = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    other_item = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE gallery_item SET editorial_state = 'published' WHERE id = ?", (ITEM_ID,)
    )
    connection.execute(
        "INSERT INTO source_record VALUES (?, ?, ?, ?, 'active', ?)",
        (
            other_record,
            other_source,
            "https://archive.example.org/cross-source",
            "c" * 64,
            "{}",
        ),
    )
    connection.execute(
        """INSERT INTO gallery_item VALUES (
               ?, 'Cross source', 'Summary', 'SIMULATION', '{}', NULL, ?,
               'published', NULL, 'Cross-source field', ?
           )""",
        (other_item, other_record, "2026-08-30 00:00:00"),
    )
    connection.execute(
        """INSERT INTO embedding VALUES (
               'cross-source-embedding', ?, 'old', 'v1', ?, NULL, ?, ?
           )""",
        (
            other_item,
            json.dumps([0.99, 0.01]),
            "2026-08-30 00:00:00",
            "2026-08-30 00:00:00",
        ),
    )
    connection.commit()
    connection.close()

    resolved = SqliteCatalogResolver(path).resolve_cluster(
        {"source_id": SOURCE_ID, "ingest_run_id": RUN_ID}
    )

    assert resolved.eligible_item_count == 2
    assert {item.item_id for item in resolved.items} == {ITEM_ID, other_item}


def render_result() -> dict[str, object]:
    return {
        "alt_text": "A synthetic Roman field",
        "credit": "NASA/STScI",
        "rights": "Public domain",
        "rights_url": None,
        "previews": [
            {
                "public_url": "https://previews.example.test/content-320.webp",
                "width": 320,
                "height": 160,
            },
            {
                "public_url": "https://previews.example.test/content-768.webp",
                "width": 768,
                "height": 384,
            },
        ],
    }


def test_render_persistence_publishes_only_gated_draft_and_enqueues_embed(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    database(path)
    resolver = SqliteCatalogResolver(path)
    render_payload = {"item_id": ITEM_ID, "product_id": PRODUCT_ID, "recipe": {"version": "v1"}}

    persisted = resolver.persist_render(render_payload, render_result())
    assert persisted["published"] is True
    assert persisted["rendition_count"] == 2

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    item = connection.execute(
        "SELECT editorial_state, metadata_json, processing_note FROM gallery_item WHERE id = ?",
        (ITEM_ID,),
    ).fetchone()
    assert item["editorial_state"] == "published"
    assert "publication_gate" not in json.loads(item["metadata_json"])
    assert item["processing_note"] is None
    generated = connection.execute(
        "SELECT * FROM rendition WHERE provider = 'romanpics' ORDER BY width"
    ).fetchall()
    assert [(row["width"], row["height"]) for row in generated] == [(320, 160), (768, 384)]
    embed_job = connection.execute(
        "SELECT * FROM jobs WHERE id = ?", (persisted["embed_job_id"],)
    ).fetchone()
    assert embed_job["job_type"] == "embed"
    assert json.loads(embed_job["payload_json"]) == {
        "item_id": ITEM_ID,
        "source_record_id": RECORD_ID,
        "checksum": CHECKSUM,
    }
    connection.close()

    # Retry is idempotent: generated rendition URLs and embed dedupe key stay unique.
    resolver.persist_render(render_payload, render_result())
    connection = sqlite3.connect(path)
    assert (
        connection.execute(
            "SELECT count(*) FROM rendition WHERE provider = 'romanpics'"
        ).fetchone()[0]
        == 2
    )
    assert (
        connection.execute("SELECT count(*) FROM jobs WHERE job_type = 'embed'").fetchone()[0] == 1
    )
    connection.close()


def test_render_persistence_does_not_publish_hidden_or_ungated_item(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    database(path)
    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE gallery_item SET editorial_state = 'hidden' WHERE id = ?", (ITEM_ID,)
    )
    connection.commit()
    connection.close()

    persisted = SqliteCatalogResolver(path).persist_render(
        {"item_id": ITEM_ID, "product_id": PRODUCT_ID, "recipe": {"version": "v1"}},
        render_result(),
    )
    assert persisted["published"] is False
    connection = sqlite3.connect(path)
    state, metadata = connection.execute(
        "SELECT editorial_state, metadata_json FROM gallery_item WHERE id = ?", (ITEM_ID,)
    ).fetchone()
    assert state == "hidden"
    assert json.loads(metadata)["publication_gate"] == "render"
    connection.close()


def test_embedding_persistence_upserts_only_current_item_source_checksum(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    database(path)
    resolver = SqliteCatalogResolver(path)
    embed_payload = {
        "item_id": ITEM_ID,
        "source_record_id": RECORD_ID,
        "checksum": CHECKSUM,
    }
    result = {
        "model": "combined:test",
        "version": "v1",
        "vector": [0.25, 0.75],
        "perceptual_hash": "0123456789abcdef",
    }
    persisted = resolver.persist_embedding(embed_payload, result)
    resolver.persist_embedding(embed_payload, {**result, "vector": [0.5, 0.5]})
    connection = sqlite3.connect(path)
    row = connection.execute(
        "SELECT * FROM embedding WHERE id = ?", (persisted["embedding_id"],)
    ).fetchone()
    assert json.loads(row[4]) == [0.5, 0.5]
    assert (
        connection.execute(
            "SELECT count(*) FROM embedding WHERE model = 'combined:test'"
        ).fetchone()[0]
        == 1
    )
    connection.close()

    try:
        resolver.persist_embedding({**embed_payload, "checksum": "b" * 64}, result)
    except LookupError:
        pass
    else:
        raise AssertionError("stale embedding should not persist")


def test_cluster_persistence_reconciles_prior_identity_and_replaces_directional_graph(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    database(path)
    second_item = "66666666-6666-4666-8666-666666666666"
    second_record = "77777777-7777-4777-8777-777777777777"
    prior_cluster = "88888888-8888-4888-8888-888888888888"
    connection = sqlite3.connect(path)
    connection.execute(
        "INSERT INTO source_record VALUES (?, ?, ?, ?, 'active', ?)",
        (
            second_record,
            SOURCE_ID,
            "https://archive.example.org/second",
            "b" * 64,
            "{}",
        ),
    )
    connection.execute(
        """INSERT INTO gallery_item VALUES (
               ?, 'Second', 'Summary', 'SIMULATION', '{}', NULL, ?,
               'published', NULL, 'A second field', ?
           )""",
        (second_item, second_record, "2026-08-30 00:00:00"),
    )
    connection.execute(
        """INSERT INTO embedding VALUES (
               'second-embedding', ?, 'old', 'v1', ?, NULL, ?, ?
           )""",
        (
            second_item,
            json.dumps([0.99, 0.01]),
            "2026-08-30 00:00:00",
            "2026-08-30 00:00:00",
        ),
    )
    connection.execute(
        "UPDATE gallery_item SET editorial_state = 'published' WHERE id = ?", (ITEM_ID,)
    )
    connection.execute(
        """INSERT INTO cluster VALUES (
               ?, 'curated-seed', 'Curated title', 'Curated summary', 'SIMULATION',
               'fixture-v1', ?, NULL, NULL, ?, ?
           )""",
        (
            prior_cluster,
            ITEM_ID,
            "2026-08-30 00:00:00",
            "2026-08-30 00:00:00",
        ),
    )
    connection.execute("INSERT INTO cluster_member VALUES (?, ?, 1.0, 0)", (prior_cluster, ITEM_ID))
    connection.commit()
    connection.close()

    payload = {"source_id": SOURCE_ID, "ingest_run_id": RUN_ID}
    result = {
        "algorithm_version": "cosine-knn-components-v1",
        "groups": [[ITEM_ID, second_item]],
        "edges": [
            {
                "left": ITEM_ID,
                "right": second_item,
                "reason": "cosine",
                "cosine": 0.99,
            }
        ],
    }
    resolver = SqliteCatalogResolver(path)
    first = resolver.persist_clusters(payload, result)
    second = resolver.persist_clusters(payload, result)

    assert first["snapshot"]["active"][0]["cluster_id"] == prior_cluster
    assert second["snapshot"]["active"][0]["cluster_id"] == prior_cluster
    assert second["active_cluster_count"] == 1
    assert second["edge_count"] == 2
    connection = sqlite3.connect(path)
    assert (
        connection.execute("SELECT title FROM cluster WHERE id = ?", (prior_cluster,)).fetchone()[0]
        == "Curated title"
    )
    assert (
        connection.execute(
            "SELECT count(*) FROM cluster_member WHERE cluster_id = ?", (prior_cluster,)
        ).fetchone()[0]
        == 2
    )
    assert connection.execute("SELECT count(*) FROM similarity_edge").fetchone()[0] == 2
    directions = set(
        connection.execute("SELECT item_id, related_item_id FROM similarity_edge").fetchall()
    )
    assert directions == {(ITEM_ID, second_item), (second_item, ITEM_ID)}
    connection.close()


def test_link_check_persistence_is_per_target_and_retry_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    database(path)
    payload = {"scope": "catalog"}
    result = {
        "job_id": "99999999-9999-4999-8999-999999999999",
        "checks": [
            {
                "url": "https://archive.example.org/shared",
                "target_kind": "source_record",
                "target_id": RECORD_ID,
                "ok": True,
                "status_code": 200,
                "final_url": "https://archive.example.org/shared",
                "error": None,
            },
            {
                "url": "https://archive.example.org/shared",
                "target_kind": "rendition",
                "target_id": "rendition-1",
                "ok": False,
                "status_code": None,
                "final_url": None,
                "error": "synthetic",
            },
        ],
    }
    resolver = SqliteCatalogResolver(path)
    assert resolver.persist_link_checks(payload, result) == {"persisted": 2}
    assert resolver.persist_link_checks(payload, result) == {"persisted": 2}

    connection = sqlite3.connect(path)
    assert connection.execute("SELECT count(*) FROM link_check").fetchone()[0] == 2
    assert (
        connection.execute(
            "SELECT count(*) FROM link_check WHERE ok = 0 AND error = 'synthetic'"
        ).fetchone()[0]
        == 1
    )
    connection.close()
