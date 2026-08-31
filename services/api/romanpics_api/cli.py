from __future__ import annotations

import asyncio
import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import httpx
import typer
from sqlalchemy import select

from .adapters import (
    IpacManifestAdapter,
    MastFixtureAdapter,
    NasaImagesAdapter,
    NasaSvsAdapter,
    ReviewedManifestAdapter,
)
from .config import Settings
from .database import build_engine, build_session_factory, create_schema
from .models import GalleryItem
from .services.ingestion import IngestionService, source_status
from .services.jobs import enqueue_link_check, retry_failed_jobs
from .services.linkcheck import check_catalog_links
from .services.seed import seed_catalog
from .services.votes import audit_suspicious_actors, rebuild_vote_totals

app = typer.Typer(no_args_is_help=True, help="RomanPics catalog operator commands")


class AdapterName(StrEnum):
    NASA_IMAGES = "nasa_images"
    NASA_SVS = "nasa_svs"
    REVIEWED_MANIFEST = "reviewed_manifest"
    IPAC_MANIFEST = "ipac_manifest"
    MAST_ROMAN = "mast_roman"


def _runtime() -> tuple[Settings, object, object]:
    settings = Settings()
    engine = build_engine(settings)
    return settings, engine, build_session_factory(engine)


@app.command("init-db")
def init_db() -> None:
    """Create tables for a local demo; production should use Alembic."""
    _, engine, _ = _runtime()
    create_schema(engine)
    typer.echo("database schema created")


@app.command()
def seed(
    manifest: Annotated[
        Path | None,
        typer.Option("--manifest", help="Normalized or shared camelCase catalog JSON"),
    ] = None,
) -> None:
    """Idempotently load the static eight-item catalog and editorial graph."""
    settings, _, factory = _runtime()
    chosen = manifest or (
        Path("data/catalog.json") if Path("data/catalog.json").exists() else settings.manifest_path
    )
    result = asyncio.run(seed_catalog(factory, chosen, settings.allowed_upstream_hosts))
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command()
def sync(
    adapter: AdapterName,
    fixture: Annotated[Path | None, typer.Option("--fixture")] = None,
    full: Annotated[bool, typer.Option("--full", help="Request a complete reconciliation")] = False,
) -> None:
    """Synchronize one source adapter; live network calls are explicit by name."""
    settings, _, factory = _runtime()

    async def run() -> object:
        if adapter == AdapterName.REVIEWED_MANIFEST:
            selected = ReviewedManifestAdapter(fixture or settings.manifest_path)
        elif adapter == AdapterName.IPAC_MANIFEST:
            selected = IpacManifestAdapter(fixture or Path("manifests/ipac-reviewed.json"))
        elif adapter == AdapterName.MAST_ROMAN:
            if fixture is None:
                raise typer.BadParameter("mast_roman requires --fixture")
            selected = MastFixtureAdapter(fixture, enabled=settings.mast_fixture_enabled)
        else:
            client = httpx.AsyncClient(timeout=30, follow_redirects=False)
            try:
                selected = (
                    NasaImagesAdapter(client)
                    if adapter == AdapterName.NASA_IMAGES
                    else NasaSvsAdapter(client)
                )
                return await IngestionService(
                    factory, settings.allowed_upstream_hosts, max_pages=settings.max_sync_pages
                ).sync(selected, full=full)
            finally:
                await client.aclose()
        return await IngestionService(
            factory, settings.allowed_upstream_hosts, max_pages=settings.max_sync_pages
        ).sync(selected, full=full)

    run_result = asyncio.run(run())
    typer.echo(
        json.dumps(
            {
                "run_id": run_result.id,
                "state": run_result.state,
                "created": run_result.created_count,
                "updated": run_result.updated_count,
                "unchanged": run_result.unchanged_count,
                "failed": run_result.failed_count,
            },
            indent=2,
        )
    )


@app.command("link-check")
def link_check(
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
) -> None:
    """Verify allowlisted source, preview, and product links without reading bodies."""
    settings, _, factory = _runtime()
    result = asyncio.run(
        check_catalog_links(
            factory,
            settings.allowed_upstream_hosts,
            timeout=settings.link_check_timeout_seconds,
            limit=limit,
        )
    )
    typer.echo(json.dumps(result, indent=2))
    if result["failed"]:
        raise typer.Exit(1)


@app.command("enqueue-link-check")
def queue_link_check(
    scope: Annotated[str, typer.Option("--scope")] = "catalog",
) -> None:
    """Queue the worker's durable, catalog-ID-hydrated link checker."""
    if scope != "catalog":
        raise typer.BadParameter("jobs-v1 currently supports only --scope catalog")
    _, _, factory = _runtime()
    session = factory()
    try:
        job, created = enqueue_link_check(session, scope=scope)
        session.commit()
        typer.echo(
            json.dumps(
                {"job_id": job.id, "created": created, "status": job.status, "scope": scope},
                indent=2,
            )
        )
    finally:
        session.close()


@app.command("retry-failed-jobs")
def retry_jobs(
    job_type: Annotated[
        str | None,
        typer.Option("--job-type", help="render, embed, cluster, or link-check"),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=1_000)] = 100,
) -> None:
    """Requeue a bounded batch of terminal worker jobs for an operator retry."""
    _, _, factory = _runtime()
    session = factory()
    try:
        try:
            identifiers = retry_failed_jobs(session, job_type=job_type, limit=limit)
        except ValueError as error:
            raise typer.BadParameter(str(error)) from error
        session.commit()
        typer.echo(json.dumps({"requeued": len(identifiers), "job_ids": identifiers}, indent=2))
    finally:
        session.close()


@app.command("source-status")
def show_source_status() -> None:
    """Print public adapter freshness and degraded-state summaries."""
    _, _, factory = _runtime()
    session = factory()
    try:
        typer.echo(json.dumps(source_status(session), indent=2, default=str))
    finally:
        session.close()


@app.command("vote-audit")
def vote_audit(
    hours: Annotated[int, typer.Option(min=1)] = 24,
    minimum_events: Annotated[int, typer.Option(min=1)] = 10,
) -> None:
    """Summarize high-volume signed-cookie actors without exposing raw IPs."""
    _, _, factory = _runtime()
    session = factory()
    try:
        rows = audit_suspicious_actors(session, hours=hours, minimum_events=minimum_events)
        typer.echo(json.dumps(rows, indent=2, default=str))
    finally:
        session.close()


@app.command("rebuild-vote-totals")
def rebuild_totals() -> None:
    _, _, factory = _runtime()
    session = factory()
    try:
        count = rebuild_vote_totals(session)
        typer.echo(f"rebuilt {count} vote totals")
    finally:
        session.close()


@app.command("editorial-state")
def editorial_state(
    slug: str,
    state: Annotated[str, typer.Argument(help="draft, published, or hidden")],
) -> None:
    """Apply a reviewed draft/publish/hide transition outside the public API."""
    if state not in {"draft", "published", "hidden"}:
        raise typer.BadParameter("state must be draft, published, or hidden")
    _, _, factory = _runtime()
    session = factory()
    try:
        item = session.scalar(select(GalleryItem).where(GalleryItem.slug == slug))
        if item is None:
            raise typer.BadParameter(f"unknown item slug: {slug}")
        previous = item.editorial_state
        item.editorial_state = state
        session.commit()
        typer.echo(f"{slug}: {previous} -> {state}")
    finally:
        session.close()
