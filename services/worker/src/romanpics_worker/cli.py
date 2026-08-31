"""Command-line entry point for local development and container workers."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from .catalog import PostgresCatalogResolver, SqliteCatalogResolver
from .contracts import JOB_TYPES
from .dedupe import hashes_for_bytes
from .handlers import build_handlers
from .jobs import Worker, open_job_store, sqlite_path_from_url
from .rendering import COLOR_RECIPES, RenderConfig, ThumbnailRenderer
from .similarity import SimilarityItem, group_similar_items
from .sources import SafeRemoteFetcher, SourcePolicy
from .storage import LocalPreviewStore


def _json_dump(value: Any) -> None:
    json.dump(value, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")


def _renderer(args: argparse.Namespace) -> ThumbnailRenderer:
    return ThumbnailRenderer(RenderConfig(sizes=tuple(args.sizes)))


def _fetcher(args: argparse.Namespace) -> SafeRemoteFetcher:
    if args.enable_network and not args.allow_host:
        raise ValueError("--enable-network requires at least one --allow-host")
    return SafeRemoteFetcher(
        SourcePolicy(
            allowed_hosts=frozenset(args.allow_host),
            max_bytes=args.max_bytes,
        ),
        enabled=args.enable_network,
    )


def _job_store(args: argparse.Namespace, *, initialize: bool = False):
    return open_job_store(
        database=args.database,
        database_url=args.database_url,
        initialize=initialize,
    )


def _catalog_resolver(args: argparse.Namespace):
    if args.database_url:
        if args.database is not None:
            raise ValueError("choose either --database or --database-url")
        if args.database_url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
            return PostgresCatalogResolver(args.database_url)
        if args.database_url.startswith("sqlite:///"):
            return SqliteCatalogResolver(sqlite_path_from_url(args.database_url))
        raise ValueError("database URL must use PostgreSQL/psycopg or SQLite")
    if args.database is None:
        raise ValueError("--database or --database-url is required")
    return SqliteCatalogResolver(args.database)


def command_render(args: argparse.Namespace) -> int:
    previews = _renderer(args).render_file(args.source, args.output, array_key=args.array_key)
    _json_dump([{**asdict(preview), "path": str(preview.path)} for preview in previews])
    return 0


def command_render_url(args: argparse.Namespace) -> int:
    renderer = _renderer(args)
    with _fetcher(args) as fetcher, fetcher.temporary_file(args.url) as (source, metadata):
        previews = renderer.render_file(source, args.output, array_key=args.array_key)
    _json_dump(
        {
            "source": asdict(metadata),
            "previews": [{**asdict(preview), "path": str(preview.path)} for preview in previews],
        }
    )
    return 0


def command_hash(args: argparse.Namespace) -> int:
    _json_dump(asdict(hashes_for_bytes(Path(args.image).read_bytes())))
    return 0


def command_recipes(_args: argparse.Namespace) -> int:
    _json_dump({name: asdict(recipe) for name, recipe in COLOR_RECIPES.items()})
    return 0


def command_group(args: argparse.Namespace) -> int:
    value = json.loads(Path(args.input).read_text())
    items = [
        SimilarityItem(
            item_id=item["item_id"],
            content_class=item["content_class"],
            embedding=np.asarray(item["embedding"], dtype=np.float32),
            family_keys=frozenset(item.get("family_keys", ())),
        )
        for item in value
    ]
    result = group_similar_items(items, cosine_threshold=args.threshold, neighbors=args.neighbors)
    _json_dump(
        {
            "algorithm_version": result.algorithm_version,
            "groups": [sorted(group) for group in result.groups],
            "edges": [asdict(edge) for edge in result.edges],
        }
    )
    return 0


def command_init_db(args: argparse.Namespace) -> int:
    with _job_store(args, initialize=True):
        pass
    return 0


def command_enqueue(args: argparse.Namespace) -> int:
    payload = json.loads(args.payload)
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    with _job_store(args) as store:
        job_id = store.enqueue(
            args.job_type,
            payload,
            priority=args.priority,
            max_attempts=args.max_attempts,
            dedupe_key=args.dedupe_key,
        )
    _json_dump({"job_id": job_id})
    return 0


def command_recover_leases(args: argparse.Namespace) -> int:
    with _job_store(args) as store:
        recovered = store.requeue_stale(stale_after=args.stale_after)
    _json_dump({"recovered": recovered})
    return 0


def command_work(args: argparse.Namespace) -> int:
    fetcher = _fetcher(args) if args.enable_network else None
    try:
        with _job_store(args) as store:
            recovered = (
                store.requeue_stale(stale_after=args.recover_stale_after)
                if args.recover_stale_after is not None
                else 0
            )
            catalog = _catalog_resolver(args)
            handlers = build_handlers(
                resolver=catalog,
                result_sink=catalog,
                fetcher=fetcher,
                preview_store=LocalPreviewStore(
                    args.preview_dir,
                    public_base_url=args.preview_base_url,
                ),
            )
            worker = Worker(
                store,
                handlers,
                worker_id=args.worker_id,
                heartbeat_interval=args.heartbeat_interval,
            )
            if args.forever:
                processed = worker.run_forever(poll_interval=args.poll_interval)
            else:
                processed = 0
                for _ in range(args.max_jobs):
                    if not worker.run_once():
                        break
                    processed += 1
        _json_dump({"processed": processed, "recovered": recovered})
        return 0
    finally:
        if fetcher is not None:
            fetcher.close()


def _add_database_options(parser: argparse.ArgumentParser) -> None:
    database = parser.add_mutually_exclusive_group(required=True)
    database.add_argument("--database", help="SQLite database path")
    database.add_argument(
        "--database-url",
        help="postgresql[+psycopg]://... or sqlite:///... URL",
    )


def _add_network_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--enable-network", action="store_true")
    parser.add_argument("--allow-host", action="append", default=[])
    parser.add_argument("--max-bytes", type=int, default=64 * 1024 * 1024)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="romanpics-worker")
    subcommands = parser.add_subparsers(dest="command", required=True)

    render = subcommands.add_parser("render", help="render a local FITS/ASDF product")
    render.add_argument("source")
    render.add_argument("--output", required=True)
    render.add_argument("--array-key")
    render.add_argument("--sizes", nargs="+", type=int, default=[320, 768])
    render.set_defaults(function=command_render)

    render_url = subcommands.add_parser("render-url", help="fetch and render an allowlisted URL")
    render_url.add_argument("url")
    render_url.add_argument("--output", required=True)
    render_url.add_argument("--array-key")
    render_url.add_argument("--sizes", nargs="+", type=int, default=[320, 768])
    _add_network_options(render_url)
    render_url.set_defaults(function=command_render_url)

    hashes = subcommands.add_parser("hash", help="compute exact and perceptual image hashes")
    hashes.add_argument("image")
    hashes.set_defaults(function=command_hash)

    recipes = subcommands.add_parser("recipes", help="print documented Roman RGB recipes")
    recipes.set_defaults(function=command_recipes)

    group = subcommands.add_parser("group", help="group an embedding JSON array")
    group.add_argument("input")
    group.add_argument("--threshold", type=float, default=0.86)
    group.add_argument("--neighbors", type=int, default=8)
    group.set_defaults(function=command_group)

    init_db = subcommands.add_parser("init-db", help="create a compatible jobs table")
    _add_database_options(init_db)
    init_db.set_defaults(function=command_init_db)

    enqueue = subcommands.add_parser("enqueue", help="enqueue a jobs-v1 JSON payload")
    _add_database_options(enqueue)
    enqueue.add_argument("job_type", choices=JOB_TYPES)
    enqueue.add_argument("payload", help="JSON object matching docs/job-contract.json")
    enqueue.add_argument("--priority", type=int, default=0)
    enqueue.add_argument("--max-attempts", type=int, default=5)
    enqueue.add_argument("--dedupe-key")
    enqueue.set_defaults(function=command_enqueue)

    recover = subcommands.add_parser("recover-leases", help="recover expired worker leases")
    _add_database_options(recover)
    recover.add_argument("--stale-after", type=float, default=300)
    recover.set_defaults(function=command_recover_leases)

    work = subcommands.add_parser("work", help="process backend jobs")
    _add_database_options(work)
    work.add_argument("--worker-id", default=f"{socket.gethostname()}-{os.getpid()}")
    work.add_argument("--max-jobs", type=int, default=1)
    work.add_argument("--forever", action="store_true")
    work.add_argument("--poll-interval", type=float, default=1.0)
    work.add_argument("--heartbeat-interval", type=float, default=30.0)
    work.add_argument("--recover-stale-after", type=float, default=300.0)
    work.add_argument("--preview-dir", default="./previews")
    work.add_argument("--preview-base-url")
    _add_network_options(work)
    work.set_defaults(function=command_work)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.function(args))
    except (KeyError, ValueError, RuntimeError) as error:
        parser.error(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
