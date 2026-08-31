from __future__ import annotations

import os
import threading
import uuid

import pytest

from romanpics_worker.catalog import PostgresCatalogResolver
from romanpics_worker.jobs import PostgresJobStore

DATABASE_URL = os.getenv("ROMANPICS_TEST_DATABASE_URL")
pytestmark = pytest.mark.postgres


def payload(index: int) -> dict[str, str]:
    return {"scope": f"catalog-{index}"}


@pytest.mark.skipif(not DATABASE_URL, reason="set ROMANPICS_TEST_DATABASE_URL for PostgreSQL")
def test_postgres_concurrent_claim_heartbeat_recovery_and_dead_letter() -> None:
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb

    dsn = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    schema = f"romanpics_worker_test_{uuid.uuid4().hex}"
    admin = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
    admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    def connection():
        value = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
        value.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        return value

    first_connection = connection()
    first = PostgresJobStore(first_connection, initialize=True)
    try:
        for index in range(4):
            first.enqueue(
                "link-check",
                payload(index),
                dedupe_key=f"job:{index}",
            )

        barrier = threading.Barrier(3)
        claimed = []
        lock = threading.Lock()

        def claim(worker_id: str) -> None:
            current_connection = connection()
            store = PostgresJobStore(current_connection)
            try:
                barrier.wait()
                job = store.claim(worker_id)
                assert job is not None
                with lock:
                    claimed.append((worker_id, job.id))
            finally:
                current_connection.close()

        threads = [threading.Thread(target=claim, args=(f"worker-{index}",)) for index in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        assert len({job_id for _worker, job_id in claimed}) == 2

        owner, stale_id = claimed[0]
        assert first.heartbeat(stale_id, owner)
        first_connection.execute(
            "UPDATE jobs SET locked_at = CURRENT_TIMESTAMP - interval '1 hour' WHERE id = %s",
            (stale_id,),
        )
        assert first.requeue_stale(stale_after=60) == 1
        assert first.get(stale_id).status == "queued"

        terminal_id = first.enqueue("link-check", payload(99), max_attempts=1)
        terminal = first.claim("terminal-worker")
        assert terminal is not None
        # Higher-priority ordering is not relevant; consume until terminal is owned.
        while terminal.id != terminal_id:
            first.complete(terminal.id, "terminal-worker", {"ok": True})
            terminal = first.claim("terminal-worker")
            assert terminal is not None
        assert first.fail(terminal.id, "terminal-worker", "synthetic", retry_delay=0) == "failed"
        assert first.get(terminal.id).status == "failed"

        first_connection.execute(
            """
            CREATE TABLE source_record (
                id varchar(36) PRIMARY KEY, source_id varchar(36), canonical_url text,
                checksum varchar(64), state varchar(32), raw_metadata jsonb
            );
            CREATE TABLE gallery_item (
                id varchar(36) PRIMARY KEY, title text, plain_summary text,
                content_class varchar(32), metadata_json jsonb,
                primary_observation_id varchar(36), primary_source_record_id varchar(36),
                editorial_state varchar(32), processing_note text, alt_text text,
                updated_at timestamptz DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE archive_product (
                id varchar(36) PRIMARY KEY, source_record_id varchar(36),
                external_url text, media_type varchar(255), active boolean
            );
            CREATE TABLE item_asset (item_id varchar(36), product_id varchar(36));
            CREATE TABLE rendition (
                id varchar(36) PRIMARY KEY, item_id varchar(36), provider varchar(100),
                url text, width integer, height integer, format varchar(100),
                is_site_derivative boolean, recipe text, alt_text text, credit text,
                rights text, rights_url text, role varchar(50),
                last_verified_at timestamptz, created_at timestamptz,
                updated_at timestamptz, UNIQUE (item_id, url)
            );
            CREATE TABLE embedding (
                id varchar(36) PRIMARY KEY, item_id varchar(36), model varchar(200),
                version varchar(100), vector jsonb, perceptual_hash varchar(128),
                created_at timestamptz, updated_at timestamptz,
                UNIQUE (item_id, model, version)
            );
            """
        )
        item_id = "11111111-1111-4111-8111-111111111111"
        product_id = "22222222-2222-4222-8222-222222222222"
        record_id = "33333333-3333-4333-8333-333333333333"
        checksum = "a" * 64
        first_connection.execute(
            "INSERT INTO source_record VALUES (%s, %s, %s, %s, 'active', %s)",
            (
                record_id,
                "44444444-4444-4444-8444-444444444444",
                "https://archive.example.org/record",
                checksum,
                Jsonb({"credit": "NASA/STScI"}),
            ),
        )
        first_connection.execute(
            """
            INSERT INTO gallery_item (
                id, title, plain_summary, content_class, metadata_json,
                primary_source_record_id, editorial_state, processing_note, alt_text
            ) VALUES (%s, 'Field', 'Summary', 'SIMULATION', %s, %s, 'draft', %s, 'Alt')
            """,
            (
                item_id,
                Jsonb({"publication_gate": "render"}),
                record_id,
                "Awaiting a bounded site-generated preview.",
            ),
        )
        first_connection.execute(
            "INSERT INTO archive_product VALUES (%s, %s, %s, 'application/fits', true)",
            (product_id, record_id, "https://archive.example.org/product.fits"),
        )
        first_connection.execute("INSERT INTO item_asset VALUES (%s, %s)", (item_id, product_id))

        gateway = PostgresCatalogResolver(dsn, search_path=schema)
        render_payload = {"item_id": item_id, "product_id": product_id, "recipe": {"version": "v1"}}
        render_result = {
            "alt_text": "Alt",
            "credit": "NASA/STScI",
            "rights": None,
            "rights_url": None,
            "previews": [
                {
                    "public_url": "https://previews.example.test/preview.webp",
                    "width": 320,
                    "height": 160,
                }
            ],
        }
        persisted = gateway.persist_render(render_payload, render_result)
        assert persisted["published"] is True
        state = first_connection.execute(
            """SELECT editorial_state, metadata_json, processing_note
               FROM gallery_item WHERE id = %s""",
            (item_id,),
        ).fetchone()
        assert state["editorial_state"] == "published"
        assert "publication_gate" not in state["metadata_json"]
        assert state["processing_note"] is None
        embed_payload = {
            "item_id": item_id,
            "source_record_id": record_id,
            "checksum": checksum,
        }
        resolved = gateway.resolve_embed(embed_payload)
        assert resolved.image_url == "https://previews.example.test/preview.webp"
        embedded = gateway.persist_embedding(
            embed_payload,
            {
                "model": "combined:test",
                "version": "v1",
                "vector": [0.25, 0.75],
                "perceptual_hash": "0123456789abcdef",
            },
        )
        assert (
            first_connection.execute(
                "SELECT count(*) AS count FROM embedding WHERE id = %s",
                (embedded["embedding_id"],),
            ).fetchone()["count"]
            == 1
        )
    finally:
        first_connection.close()
        admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        admin.close()
