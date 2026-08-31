from __future__ import annotations

import io
import sqlite3
import threading
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from PIL import Image

from romanpics_worker.catalog import (
    LinkTarget,
    ResolvedClusterInput,
    ResolvedEmbedInput,
    ResolvedRenderInput,
)
from romanpics_worker.handlers import build_handlers
from romanpics_worker.jobs import JobStore, Worker
from romanpics_worker.similarity import SimilarityItem
from romanpics_worker.sources import SafeRemoteFetcher, SourcePolicy
from romanpics_worker.storage import LocalPreviewStore

ITEM_ID = "11111111-1111-4111-8111-111111111111"
PRODUCT_ID = "22222222-2222-4222-8222-222222222222"
RECORD_ID = "33333333-3333-4333-8333-333333333333"
SOURCE_ID = "44444444-4444-4444-8444-444444444444"
RUN_ID = "55555555-5555-4555-8555-555555555555"
CHECKSUM = "a" * 64


def payload(job_type: str) -> dict[str, object]:
    return {
        "render": {"item_id": ITEM_ID, "product_id": PRODUCT_ID, "recipe": {"version": "v1"}},
        "embed": {"item_id": ITEM_ID, "source_record_id": RECORD_ID, "checksum": CHECKSUM},
        "cluster": {"source_id": SOURCE_ID, "ingest_run_id": RUN_ID},
        "link-check": {"scope": "catalog"},
    }[job_type]


class Clock:
    def __init__(self, value: datetime | None = None):
        self.value = value or datetime(2026, 8, 30, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value


def handlers_with(job_type: str, handler):
    def default(job):
        return {"handled": job.job_type}

    handlers = {kind: default for kind in ("render", "embed", "cluster", "link-check")}
    handlers[job_type] = handler
    return handlers


def test_job_claim_priority_completion_and_global_dedupe() -> None:
    clock = Clock()
    connection = sqlite3.connect(":memory:", isolation_level=None)
    store = JobStore(connection, clock=clock)
    low = store.enqueue("link-check", payload("link-check"), priority=0, dedupe_key="one")
    assert store.enqueue("link-check", payload("link-check"), dedupe_key="one") == low
    high = store.enqueue("cluster", payload("cluster"), priority=10)

    claimed = store.claim("worker-a")
    assert claimed is not None and claimed.id == high and claimed.attempts == 1
    store.complete(claimed.id, "worker-a", {"ok": True})
    assert store.get(high).status == "succeeded"
    assert store.result(high) == {"ok": True}
    assert store.claim("worker-b").id == low


def test_worker_retries_with_backoff_then_dead_letters_as_failed() -> None:
    clock = Clock()
    store = JobStore(sqlite3.connect(":memory:", isolation_level=None), clock=clock)
    job_id = store.enqueue("link-check", payload("link-check"), max_attempts=2)

    def fail(_job):
        raise ValueError("synthetic")

    worker = Worker(
        store,
        handlers_with("link-check", fail),
        worker_id="worker",
        base_retry_delay=5,
        heartbeat_interval=0,
    )
    assert worker.run_once()
    assert store.get(job_id).status == "queued"
    assert store.get(job_id).available_at == clock.value + timedelta(seconds=5)
    assert not worker.run_once()
    clock.value += timedelta(seconds=5)
    assert worker.run_once()
    assert store.get(job_id).status == "failed"
    assert "synthetic" in store.error(job_id)


def test_stale_lease_recovery_and_ownership() -> None:
    clock = Clock()
    store = JobStore(sqlite3.connect(":memory:", isolation_level=None), clock=clock)
    job_id = store.enqueue("cluster", payload("cluster"))
    assert store.claim("lost").id == job_id
    with pytest.raises(RuntimeError, match="not owned"):
        store.complete(job_id, "other")
    clock.value += timedelta(seconds=100)
    assert store.requeue_stale(stale_after=30) == 1
    assert store.get(job_id).status == "queued"


def test_sqlite_concurrent_claimers_never_receive_the_same_job(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    with JobStore(database) as seed:
        for index in range(12):
            seed.enqueue(
                "link-check",
                payload("link-check"),
                dedupe_key=f"link-check:{index}",
            )

    barrier = threading.Barrier(5)
    claimed: list[str] = []
    lock = threading.Lock()

    def claim(worker: str) -> None:
        with JobStore(database, initialize=False) as store:
            barrier.wait()
            job = store.claim(worker)
            assert job is not None
            with lock:
                claimed.append(job.id)

    threads = [threading.Thread(target=claim, args=(f"worker-{index}",)) for index in range(4)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()
    assert len(claimed) == 4
    assert len(set(claimed)) == 4


class FakeResponse:
    def __init__(self, status: int, headers: Mapping[str, str], chunks: Iterable[bytes] = ()):
        self.status_code = status
        self.headers = dict(headers)
        self.chunks = list(chunks)

    def iter_bytes(self, chunk_size: int = 65_536) -> Iterator[bytes]:
        yield from self.chunks

    def close(self) -> None:
        pass


class FakeTransport:
    def __init__(self, routes: Mapping[tuple[str, str], list[FakeResponse]]):
        self.routes = {key: list(responses) for key, responses in routes.items()}
        self.requests: list[tuple[str, str]] = []

    def request(
        self, method: str, url: str, *, headers: Mapping[str, str] | None = None
    ) -> FakeResponse:
        self.requests.append((method, url))
        return self.routes[(method, url)].pop(0)

    def get(self, url: str) -> FakeResponse:
        return self.request("GET", url)

    def close(self) -> None:
        pass


class FakeResolver:
    render_url = "https://archive.example.org/product.fits"
    embed_url = "https://archive.example.org/preview.png"
    link_url = "https://archive.example.org/catalog"

    def resolve_render(self, _payload) -> ResolvedRenderInput:
        return ResolvedRenderInput(self.render_url, "application/fits")

    def resolve_embed(self, _payload) -> ResolvedEmbedInput:
        return ResolvedEmbedInput(self.embed_url, {"title": "Synthetic field"})

    def resolve_cluster(self, _payload) -> ResolvedClusterInput:
        return ResolvedClusterInput(
            items=(
                SimilarityItem("a", "SIMULATION", np.array([1.0, 0.0])),
                SimilarityItem("b", "SIMULATION", np.array([0.99, 0.01])),
            )
        )

    def resolve_link_targets(self, _payload) -> Sequence[LinkTarget]:
        return (LinkTarget(self.link_url, "source_record", RECORD_ID),)


class FakeResultSink:
    def __init__(self):
        self.rendered = []
        self.embedded = []
        self.clustered = []
        self.link_checks = []

    def persist_render(self, payload, result):
        self.rendered.append((payload, result))
        return {"published": True, "embed_job_id": "queued-embed", "rendition_count": 2}

    def persist_embedding(self, payload, result):
        self.embedded.append((payload, result))
        return {"embedding_id": "stored-embedding", "model": result["model"], "version": "v1"}

    def persist_clusters(self, payload, result):
        self.clustered.append((payload, result))
        return {
            "algorithm_version": result["algorithm_version"],
            "snapshot": {
                "run_id": payload["ingest_run_id"],
                "active": [
                    {
                        "cluster_id": "stored-cluster",
                        "version": 1,
                        "members": result["groups"][0],
                        "created_run": payload["ingest_run_id"],
                        "updated_run": payload["ingest_run_id"],
                        "predecessors": [],
                    }
                ],
            },
            "archived": [],
            "lineage": [],
            "active_cluster_count": 1,
            "archived_cluster_count": 0,
            "edge_count": 2,
        }

    def persist_link_checks(self, payload, result):
        self.link_checks.append((payload, result))
        return {"persisted": len(result["checks"])}


def fits_bytes() -> bytes:
    buffer = io.BytesIO()
    fits.PrimaryHDU(np.arange(400, dtype=np.float32).reshape(20, 20)).writeto(buffer)
    return buffer.getvalue()


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(np.arange(300, dtype=np.uint8).reshape(10, 10, 3)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_all_four_backend_payloads_are_resolved_and_handled_without_payload_urls(
    tmp_path: Path,
) -> None:
    resolver = FakeResolver()
    transport = FakeTransport(
        {
            ("GET", resolver.render_url): [
                FakeResponse(200, {"content-type": "application/fits"}, [fits_bytes()])
            ],
            ("GET", resolver.embed_url): [
                FakeResponse(200, {"content-type": "image/png"}, [png_bytes()])
            ],
            ("HEAD", resolver.link_url): [FakeResponse(200, {})],
        }
    )
    fetcher = SafeRemoteFetcher(
        SourcePolicy(allowed_hosts=frozenset({"archive.example.org"})),
        enabled=True,
        transport=transport,
        resolver=lambda _host: ["93.184.216.34"],
    )
    preview_store = LocalPreviewStore(
        tmp_path / "published", public_base_url="https://previews.example.test"
    )
    result_sink = FakeResultSink()
    handlers = build_handlers(
        resolver=resolver,
        result_sink=result_sink,
        fetcher=fetcher,
        preview_store=preview_store,
    )
    store = JobStore(sqlite3.connect(":memory:", isolation_level=None))
    job_ids = {
        kind: store.enqueue(
            kind,
            {
                **payload(kind),
                **(
                    {"recipe": {"version": "v1", "url": "https://evil.invalid/file"}}
                    if kind == "render"
                    else {}
                ),
            },
        )
        for kind in ("render", "embed", "cluster", "link-check")
    }
    worker = Worker(store, handlers, worker_id="worker", heartbeat_interval=0)
    while worker.run_once():
        pass

    assert {kind: store.get(job_id).status for kind, job_id in job_ids.items()} == {
        "render": "succeeded",
        "embed": "succeeded",
        "cluster": "succeeded",
        "link-check": "succeeded",
    }
    render_result = store.result(job_ids["render"])
    assert render_result["source_url"] == resolver.render_url
    assert all("path" not in preview for preview in render_result["previews"])
    assert ("GET", "https://evil.invalid/file") not in transport.requests
    assert store.result(job_ids["embed"])["dimension"] > 0
    assert store.result(job_ids["cluster"])["snapshot"]["active"]
    assert store.result(job_ids["link-check"])["ok"] == 1
    assert len(result_sink.rendered) == 1
    assert len(result_sink.embedded) == 1
    assert len(result_sink.clustered) == 1
    assert len(result_sink.link_checks) == 1


def test_site_generated_embedding_reads_preview_volume_without_network(tmp_path: Path) -> None:
    class SiteResolver(FakeResolver):
        def resolve_embed(self, _payload) -> ResolvedEmbedInput:
            return ResolvedEmbedInput(
                "https://previews.example.test/generated.webp",
                {"title": "Generated preview"},
                site_generated=True,
            )

    resolver = SiteResolver()
    store = LocalPreviewStore(
        tmp_path / "published", public_base_url="https://previews.example.test"
    )
    source = tmp_path / "generated.webp"
    source.write_bytes(png_bytes())
    store.put_file("generated.webp", source, content_type="image/webp")
    sink = FakeResultSink()
    handler = build_handlers(
        resolver=resolver,
        result_sink=sink,
        preview_store=store,
        fetcher=None,
    )["embed"]
    jobs = JobStore(sqlite3.connect(":memory:", isolation_level=None))
    job_id = jobs.enqueue("embed", payload("embed"))
    job = jobs.claim("worker")
    assert job is not None and job.id == job_id

    result = handler(job)

    assert result["source_transport"] == "local-preview-volume"
    assert result["dimension"] > 0
    assert len(sink.embedded) == 1


def test_cluster_refresh_defers_until_every_published_item_is_embedded() -> None:
    class IncompleteResolver(FakeResolver):
        def resolve_cluster(self, _payload) -> ResolvedClusterInput:
            return ResolvedClusterInput(
                items=(SimilarityItem("a", "SIMULATION", np.array([1.0, 0.0])),),
                eligible_item_count=2,
            )

    sink = FakeResultSink()
    handler = build_handlers(resolver=IncompleteResolver(), result_sink=sink)["cluster"]
    jobs = JobStore(sqlite3.connect(":memory:", isolation_level=None))
    jobs.enqueue("cluster", payload("cluster"))
    job = jobs.claim("worker")
    assert job is not None

    with pytest.raises(RuntimeError, match="deferred"):
        handler(job)
    assert sink.clustered == []


def test_site_generated_link_check_reads_preview_volume_without_network(tmp_path: Path) -> None:
    class SiteResolver(FakeResolver):
        def resolve_link_targets(self, _payload) -> Sequence[LinkTarget]:
            return (
                LinkTarget(
                    "https://previews.example.test/generated.webp",
                    "rendition",
                    "rendition-generated",
                    site_generated=True,
                ),
            )

    store = LocalPreviewStore(
        tmp_path / "published", public_base_url="https://previews.example.test"
    )
    source = tmp_path / "generated.webp"
    source.write_bytes(b"preview")
    store.put_file("generated.webp", source)
    sink = FakeResultSink()
    handler = build_handlers(
        resolver=SiteResolver(), result_sink=sink, preview_store=store, fetcher=None
    )["link-check"]
    jobs = JobStore(sqlite3.connect(":memory:", isolation_level=None))
    jobs.enqueue("link-check", payload("link-check"))
    job = jobs.claim("worker")
    assert job is not None

    result = handler(job)

    assert result["ok"] == 1
    assert result["failed"] == 0
    assert sink.link_checks[0][1]["checks"][0]["status_code"] == 200


def test_local_preview_store_returns_storage_uri_and_only_explicit_public_url(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.webp"
    source.write_bytes(b"preview")
    private_store = LocalPreviewStore(tmp_path / "private")
    private = private_store.put_file("ab/example.webp", source)
    assert private.storage_uri == "local://ab/example.webp"
    assert private.public_url is None
    assert (tmp_path / "private" / "ab" / "example.webp").read_bytes() == b"preview"

    public_store = LocalPreviewStore(
        tmp_path / "public", public_base_url="https://img.example.test/"
    )
    public = public_store.put_file("folder with spaces/example.webp", source)
    assert public.public_url == "https://img.example.test/folder%20with%20spaces/example.webp"
    assert public_store.read_public_url(public.public_url) == b"preview"
    assert (
        public_store.read_public_url("https://evil.example/folder%20with%20spaces/example.webp")
        is None
    )
    assert public_store.read_public_url("https://img.example.test/%2e%2e/escape.webp") is None
    assert (
        public_store.read_public_url("https://img.example.test/folder%2Fwith%2Fspaces/example.webp")
        is None
    )
    with pytest.raises(ValueError):
        public_store.put_file("../escape.webp", source)


def test_handler_registry_and_worker_reject_non_contract_job_types() -> None:
    assert set(build_handlers()) == {"render", "embed", "cluster", "link-check"}
    with pytest.raises(ValueError, match="handlers must be exactly"):
        Worker(None, {"custom": lambda _job: {}}, worker_id="bad")
