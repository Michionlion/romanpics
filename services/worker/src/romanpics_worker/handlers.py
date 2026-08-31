"""Handlers for the four backend-defined RomanPics job types."""

from __future__ import annotations

import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from .catalog import JobInputResolver, JobResultSink
from .clustering import StableClusterReconciler
from .contracts import ClusterPayload, EmbedPayload, LinkCheckPayload, RenderPayload
from .dedupe import hashes_for_bytes
from .embeddings import CombinedEmbedder
from .jobs import Handler, Job
from .rendering import ThumbnailRenderer
from .similarity import group_similar_items
from .sources import SafeRemoteFetcher
from .storage import PreviewStore


def build_handlers(
    *,
    resolver: JobInputResolver | None = None,
    result_sink: JobResultSink | None = None,
    fetcher: SafeRemoteFetcher | None = None,
    preview_store: PreviewStore | None = None,
    renderer: ThumbnailRenderer | None = None,
    embedder: CombinedEmbedder | None = None,
    reconciler: StableClusterReconciler | None = None,
) -> dict[str, Handler]:
    """Build handlers whose payload shapes exactly match ``jobs-v1``.

    Queue payloads contain only catalog IDs, checksums, recipes, and a fixed scope.
    The resolver obtains any URL from trusted catalog rows; the fetcher independently
    enforces its host/DNS/redirect policy before a request.
    """

    thumbnails = renderer or ThumbnailRenderer()
    embeddings = embedder or CombinedEmbedder()

    def dependencies(
        *, network: bool = False, storage: bool = False, persistence: bool = False
    ) -> JobInputResolver:
        if resolver is None:
            raise RuntimeError("catalog input resolver is not configured")
        if network and fetcher is None:
            raise RuntimeError("network access is not explicitly enabled and allowlisted")
        if storage and preview_store is None:
            raise RuntimeError("preview storage is not configured")
        if persistence and result_sink is None:
            raise RuntimeError("catalog result persistence is not configured")
        return resolver

    def render(job: Job) -> dict[str, Any]:
        catalog = dependencies(network=True, storage=True, persistence=True)
        payload = cast(RenderPayload, job.payload)
        resolved = catalog.resolve_render(payload)
        recipe = payload["recipe"]
        # URLs and paths in recipes are deliberately ignored: only the catalog-linked
        # archive product may become the source.
        array_key_value = recipe.get("array_key")
        if array_key_value is not None and not isinstance(array_key_value, str):
            raise ValueError("recipe.array_key must be a string when provided")
        recipe_name = str(recipe.get("name") or recipe.get("version") or "monochrome-v1")
        assert fetcher is not None and preview_store is not None
        with (
            fetcher.temporary_file(resolved.source_url) as (source, source_metadata),
            tempfile.TemporaryDirectory(prefix="romanpics-render-") as staging,
        ):
            previews = thumbnails.render_file(
                source,
                Path(staging),
                array_key=cast(str | None, array_key_value),
            )
            stored = [
                preview_store.put_file(preview.path.name, preview.path) for preview in previews
            ]
        result: dict[str, Any] = {
            "item_id": payload["item_id"],
            "product_id": payload["product_id"],
            "source_url": source_metadata.final_url,
            "source_media_type": resolved.media_type,
            "recipe": recipe,
            "recipe_name": recipe_name,
            "alt_text": resolved.alt_text,
            "credit": resolved.credit,
            "rights": resolved.rights,
            "rights_url": resolved.rights_url,
            "previews": [
                {
                    "size": preview.size,
                    "width": preview.width,
                    "height": preview.height,
                    "content_digest": preview.digest,
                    **asdict(stored_preview),
                }
                for preview, stored_preview in zip(previews, stored, strict=True)
            ],
        }
        assert result_sink is not None
        result["persistence"] = dict(result_sink.persist_render(payload, result))
        return result

    def embed(job: Job) -> dict[str, Any]:
        catalog = dependencies(persistence=True)
        payload = cast(EmbedPayload, job.payload)
        resolved = catalog.resolve_embed(payload)
        source_transport = "upstream"
        if resolved.site_generated:
            if preview_store is None:
                raise RuntimeError("site-generated embedding requires preview storage")
            image_bytes = preview_store.read_public_url(resolved.image_url)
            if image_bytes is None:
                raise RuntimeError("site-generated rendition is not present in preview storage")
            source_url = resolved.image_url
            source_transport = "local-preview-volume"
        else:
            if fetcher is None:
                raise RuntimeError("network access is not explicitly enabled and allowlisted")
            image_bytes, source_metadata = fetcher.fetch_bytes(resolved.image_url)
            source_url = source_metadata.final_url
        hashes = hashes_for_bytes(image_bytes)
        vector = embeddings.embed(image_bytes, resolved.metadata)
        result: dict[str, Any] = {
            "item_id": payload["item_id"],
            "source_record_id": payload["source_record_id"],
            "source_checksum": payload["checksum"],
            "source_url": source_url,
            "source_transport": source_transport,
            "provider": embeddings.provider_name,
            "model": embeddings.provider_name,
            "version": "v1",
            "dimension": int(vector.size),
            "vector": vector.tolist(),
            "sha256": hashes.sha256,
            "perceptual_hash": hashes.phash,
        }
        assert result_sink is not None
        result["persistence"] = dict(result_sink.persist_embedding(payload, result))
        return result

    def cluster(job: Job) -> dict[str, Any]:
        catalog = dependencies(persistence=True)
        payload = cast(ClusterPayload, job.payload)
        resolved = catalog.resolve_cluster(payload)
        if (
            resolved.eligible_item_count is not None
            and len(resolved.items) != resolved.eligible_item_count
        ):
            missing = resolved.eligible_item_count - len(resolved.items)
            raise RuntimeError(
                f"cluster refresh deferred until {missing} published item(s) have embeddings"
            )
        grouping = group_similar_items(resolved.items)
        candidate = {
            "source_id": payload["source_id"],
            "ingest_run_id": payload["ingest_run_id"],
            "algorithm_version": grouping.algorithm_version,
            "groups": [sorted(group) for group in grouping.groups],
            "edges": [asdict(edge) for edge in grouping.edges],
        }
        assert result_sink is not None
        persisted = dict(result_sink.persist_clusters(payload, candidate))
        return {
            "source_id": payload["source_id"],
            "ingest_run_id": payload["ingest_run_id"],
            **persisted,
        }

    def link_check(job: Job) -> dict[str, Any]:
        catalog = dependencies(persistence=True)
        payload = cast(LinkCheckPayload, job.payload)
        targets = catalog.resolve_link_targets(payload)
        probes: dict[tuple[str, bool], dict[str, Any]] = {}
        checks: list[dict[str, Any]] = []
        for target in targets:
            probe_key = (target.url, target.site_generated)
            probe = probes.get(probe_key)
            if probe is None:
                try:
                    if target.site_generated:
                        if preview_store is None:
                            raise RuntimeError("site-generated link check requires preview storage")
                        if preview_store.read_public_url(target.url) is None:
                            raise FileNotFoundError(
                                "site-generated rendition is not present in preview storage"
                            )
                        probe = {
                            "ok": True,
                            "status_code": 200,
                            "final_url": target.url,
                            "error": None,
                        }
                    else:
                        if fetcher is None:
                            raise RuntimeError(
                                "network access is not explicitly enabled and allowlisted"
                            )
                        metadata = fetcher.probe(target.url)
                        probe = {
                            "ok": True,
                            "status_code": metadata.status_code,
                            "final_url": metadata.final_url,
                            "error": None,
                        }
                except Exception as error:  # Preserve the batch when one upstream link fails.
                    probe = {
                        "ok": False,
                        "status_code": None,
                        "final_url": None,
                        "error": f"{type(error).__name__}: {error}"[:2000],
                    }
                probes[probe_key] = probe
            checks.append(
                {
                    "target_kind": target.target_kind,
                    "target_id": target.target_id,
                    "url": target.url,
                    **probe,
                }
            )
        candidate = {"job_id": job.id, "checks": checks}
        assert result_sink is not None
        persistence = dict(result_sink.persist_link_checks(payload, candidate))
        failures = [check for check in checks if not check["ok"]]
        ok = len(checks) - len(failures)
        return {
            "scope": payload["scope"],
            "checked": len(checks),
            "unique_urls": len({target.url for target in targets}),
            "ok": ok,
            "failed": len(failures),
            "failures": failures[:100],
            "failures_truncated": max(0, len(failures) - 100),
            "persistence": persistence,
        }

    return {
        "render": render,
        "embed": embed,
        "cluster": cluster,
        "link-check": link_check,
    }
