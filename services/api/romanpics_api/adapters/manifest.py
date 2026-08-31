from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import (
    NormalizedObservation,
    NormalizedProduct,
    NormalizedRecord,
    NormalizedRendition,
    SourceAdapter,
    SourcePage,
)
from .common import parse_datetime, slugify


class ReviewedManifestAdapter(SourceAdapter):
    name = "reviewed_manifest"
    display_name = "RomanPics reviewed manifest"
    canonical_host = "romanpics.local"
    terms_url = None

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _load(self) -> dict[str, Any]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            raise ValueError("manifest schema_version must be 1")
        if not isinstance(payload.get("records"), list):
            raise ValueError("manifest records must be a list")
        return payload

    async def discover(
        self, cursor: str | None = None, modified_since: datetime | None = None
    ) -> SourcePage:
        payload = self._load()
        records = payload["records"]
        start = int(cursor or 0)
        page_size = max(1, int(payload.get("page_size", 100)))
        page = records[start : start + page_size]
        next_cursor = str(start + page_size) if start + page_size < len(records) else None
        return SourcePage(records=page, next_cursor=next_cursor)

    async def normalize(self, record: dict[str, Any]) -> NormalizedRecord:
        required = (
            "external_id",
            "canonical_url",
            "title",
            "summary",
            "content_class",
            "alt_text",
            "credit",
        )
        missing = [key for key in required if not record.get(key)]
        if missing:
            raise ValueError(f"manifest record missing: {', '.join(missing)}")
        observation_payload = record.get("observation")
        observation = None
        if observation_payload:
            observation = NormalizedObservation(
                observation_id=str(observation_payload["observation_id"]),
                mission=str(observation_payload.get("mission", "Roman")),
                program_id=observation_payload.get("program_id"),
                survey=observation_payload.get("survey"),
                instrument=observation_payload.get("instrument"),
                mode=observation_payload.get("mode"),
                optical_elements=list(observation_payload.get("optical_elements", [])),
                target=observation_payload.get("target"),
                ra=_float_or_none(observation_payload.get("ra")),
                dec=_float_or_none(observation_payload.get("dec")),
                observed_start=parse_datetime(observation_payload.get("observed_start")),
                observed_end=parse_datetime(observation_payload.get("observed_end")),
                data_level=observation_payload.get("data_level"),
                product_version=observation_payload.get("product_version"),
                pipeline_version=observation_payload.get("pipeline_version"),
                release_name=observation_payload.get("release_name"),
            )
        products = [
            NormalizedProduct(
                url=str(item["url"]),
                subtype=str(item.get("subtype", "source")),
                media_type=str(item.get("media_type", "application/octet-stream")),
                byte_size=_int_or_none(item.get("byte_size")),
                is_original=bool(item.get("is_original", False)),
                data_level=item.get("data_level"),
            )
            for item in record.get("products", [])
        ]
        renditions = [
            NormalizedRendition(
                url=str(item["url"]),
                width=max(1, int(item.get("width", 1))),
                height=max(1, int(item.get("height", 1))),
                format=str(item.get("format", "image/jpeg")),
                provider=str(item.get("provider", record.get("provider", self.display_name))),
                alt_text=str(item.get("alt_text", record["alt_text"])),
                credit=str(item.get("credit", record["credit"])),
                rights=item.get("rights", record.get("rights")),
                rights_url=item.get("rights_url", record.get("rights_url")),
                site_generated=bool(item.get("site_generated", False)),
                transformation=item.get("transformation"),
                role=str(item.get("role", "preview")),
            )
            for item in record.get("renditions", [])
        ]
        return NormalizedRecord(
            external_id=str(record["external_id"]),
            canonical_url=str(record["canonical_url"]),
            slug=str(record.get("slug") or slugify(str(record["title"]))),
            title=str(record["title"]),
            summary=str(record["summary"]),
            content_class=str(record["content_class"]),
            is_flight_data=bool(record.get("is_flight_data", False)),
            alt_text=str(record["alt_text"]),
            credit=str(record["credit"]),
            raw=record,
            published_at=parse_datetime(record.get("published_at")),
            upstream_created_at=parse_datetime(record.get("upstream_created_at")),
            upstream_updated_at=parse_datetime(record.get("upstream_updated_at")),
            etag=record.get("etag"),
            rights=record.get("rights"),
            rights_url=record.get("rights_url"),
            processing_note=record.get("processing_note"),
            tags=[str(tag) for tag in record.get("tags", [])],
            observation=observation,
            products=products,
            renditions=renditions,
            metadata=dict(record.get("metadata", {})),
            supersedes_external_id=record.get("supersedes_external_id"),
        )


class IpacManifestAdapter(ReviewedManifestAdapter):
    """Human-reviewed bridge for IPAC simulations without a stable catalog API."""

    name = "ipac_manifest"
    display_name = "Reviewed IPAC/IRSA Roman simulations"
    canonical_host = "irsa.ipac.caltech.edu"
    terms_url = "https://irsa.ipac.caltech.edu/data_use_terms.html"


class StaticCatalogAdapter(ReviewedManifestAdapter):
    """Normalize the shared frontend catalog or the packaged canonical fixture."""

    name = "static_catalog"
    display_name = "RomanPics launch-era catalog"

    def _load(self) -> dict[str, Any]:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if (
            isinstance(raw, dict)
            and raw.get("schema_version") == 1
            and isinstance(raw.get("records"), list)
        ):
            return raw
        return _convert_frontend_catalog(raw)


class MastFixtureAdapter(ReviewedManifestAdapter):
    name = "mast_roman"
    display_name = "MAST Roman fixture"
    canonical_host = "mast.stsci.edu"
    terms_url = "https://archive.stsci.edu/publishing/data-use"

    def __init__(self, path: str | Path, *, enabled: bool = False):
        if not enabled:
            raise RuntimeError(
                "MAST fixture adapter is disabled; set MAST_FIXTURE_ENABLED=true explicitly"
            )
        super().__init__(path)


def _int_or_none(value: Any) -> int | None:
    return None if value in (None, "") else int(value)


def _float_or_none(value: Any) -> float | None:
    return None if value in (None, "") else float(value)


def _convert_frontend_catalog(raw: Any) -> dict[str, Any]:
    if isinstance(raw, list):
        items = raw
        container: dict[str, Any] = {}
    elif isinstance(raw, dict):
        items = raw.get("items") or raw.get("catalog") or raw.get("records")
        container = raw
    else:
        raise ValueError("catalog manifest must be an object or item array")
    if not isinstance(items, list):
        raise ValueError("camelCase catalog must contain an items array")

    records: list[dict[str, Any]] = []
    image_to_slug: dict[str, str] = {}
    class_map = {
        "mission-photo": "MISSION_PHOTO",
        "mission photos": "MISSION_PHOTO",
        "mission photo": "MISSION_PHOTO",
        "telescope": "GROUND_TEST",
        "the telescope": "GROUND_TEST",
        "simulations": "SIMULATION",
        "simulation": "SIMULATION",
        "visualizations": "VISUALIZATION",
        "visualization": "VISUALIZATION",
        "ground tests": "GROUND_TEST",
        "ground test": "GROUND_TEST",
        "flight-science": "FLIGHT_SCIENCE",
        "flight science": "FLIGHT_SCIENCE",
    }
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("catalog items must be objects")
        slug = str(item.get("slug") or item.get("id") or slugify(str(item.get("title", ""))))
        preview_value = item.get("preview")
        preview_object = preview_value if isinstance(preview_value, dict) else {}
        source_object = item.get("source") if isinstance(item.get("source"), dict) else {}
        image = str(
            preview_object.get("url")
            or item.get("thumbnail")
            or item.get("previewUrl")
            or (preview_value if isinstance(preview_value, str) else "")
            or item.get("image")
            or ""
        )
        canonical_url = str(
            item.get("href")
            or item.get("sourceUrl")
            or item.get("canonicalUrl")
            or source_object.get("sourceUrl")
            or source_object.get("source_url")
            or source_object.get("url")
            or ""
        )
        raw_class = str(item.get("contentClass") or item.get("content_class") or "").strip()
        content_class = class_map.get(raw_class.lower(), raw_class.upper())
        provider = str(
            item.get("provider")
            or source_object.get("provider")
            or _provider_from_url(canonical_url)
        )
        external_id = str(
            item.get("externalId")
            or item.get("external_id")
            or source_object.get("externalId")
            or source_object.get("external_id")
            or _external_id(canonical_url, slug)
        )
        alt = str(item.get("alt") or item.get("altText") or item.get("alt_text") or "")
        credit = str(item.get("credit") or source_object.get("credit") or "NASA")
        summary = str(
            item.get("summary")
            or item.get("detail")
            or item.get("description")
            or item.get("title")
            or ""
        )
        record = {
            "external_id": external_id,
            "slug": slug,
            "provider": provider,
            "canonical_url": canonical_url,
            "title": str(item.get("title") or slug.replace("-", " ").title()),
            "summary": summary,
            "content_class": content_class,
            "is_flight_data": bool(item.get("isFlightData", content_class == "FLIGHT_SCIENCE")),
            "published_at": item.get("publishedAt") or item.get("published_at"),
            "alt_text": alt,
            "credit": credit,
            "rights": item.get("rights")
            or source_object.get("rights")
            or "See the source item for credits and usage details.",
            "rights_url": item.get("rightsUrl")
            or item.get("rights_url")
            or source_object.get("rightsUrl")
            or source_object.get("rights_url")
            or "https://www.nasa.gov/nasa-brand-center/images-and-media/",
            "tags": item.get("tags") or [],
            "metadata": {
                **dict(item.get("metadata") or {}),
                "provider": provider,
                "legacy_vote_hint": item.get("votes", 0),
            },
            "products": _frontend_products(item, image),
            "renditions": item.get("renditions")
            or [
                {
                    "url": image,
                    "width": item.get("width") or preview_object.get("width") or 1280,
                    "height": item.get("height") or preview_object.get("height") or 720,
                    "format": preview_object.get("format") or _image_type(image),
                    "provider": provider,
                }
            ],
        }
        records.append(record)
        image_to_slug[image] = slug

    clusters: list[dict[str, Any]] = []
    mixed_collections: list[dict[str, Any]] = []
    for group in container.get("clusters") or container.get("groups") or []:
        member_slugs = [
            image_to_slug.get(_member_key(value), _member_key(value))
            for value in (
                group.get("items")
                or group.get("itemSlugs")
                or group.get("memberSlugs")
                or group.get("itemIds")
                or group.get("images")
                or []
            )
        ]
        member_classes = {
            record["content_class"] for record in records if record["slug"] in member_slugs
        }
        definition = {
            "slug": str(group.get("slug") or group.get("id")),
            "title": str(group.get("title")),
            "summary": str(group.get("summary") or group.get("description") or ""),
            "items": member_slugs,
        }
        if len(member_classes) == 1:
            definition["content_class"] = next(iter(member_classes))
            representative = _member_key(
                group.get("representative") or group.get("representativeSlug") or member_slugs[0]
            )
            definition["representative"] = image_to_slug.get(representative, representative)
            definition["algorithm_version"] = str(group.get("algorithmVersion") or "static-v1")
            clusters.append(definition)
        else:
            mixed_collections.append(definition)
    collections = [
        {
            "slug": str(value.get("slug") or value.get("id")),
            "title": str(value.get("title")),
            "summary": str(value.get("summary") or value.get("description") or ""),
            "items": [
                image_to_slug.get(_member_key(member), _member_key(member))
                for member in (
                    value.get("items")
                    or value.get("itemSlugs")
                    or value.get("memberSlugs")
                    or value.get("itemIds")
                    or value.get("images")
                    or []
                )
            ],
            "published": bool(value.get("published", True)),
        }
        for value in (container.get("collections") or [])
    ] + mixed_collections
    return {
        "schema_version": 1,
        "records": records,
        "clusters": clusters,
        "collections": collections,
        "similarities": [
            {
                **value,
                "algorithm_version": value.get("algorithm_version")
                or value.get("algorithmVersion")
                or "fixture-v1",
            }
            for value in (container.get("similarities") or [])
        ],
    }


def _provider_from_url(url: str) -> str:
    if "images.nasa.gov" in url:
        return "NASA_IMAGES"
    if "svs.gsfc.nasa.gov" in url:
        return "NASA_SVS"
    if "stsci.edu" in url:
        return "MAST_ROMAN"
    if "ipac.caltech.edu" in url:
        return "IPAC_IRSA"
    return "UPSTREAM"


def _external_id(url: str, fallback: str) -> str:
    parts = url.rstrip("/").split("/")
    if "/details/" in url or "svs.gsfc.nasa.gov" in url:
        return parts[-1] or fallback
    return fallback


def _image_type(url: str) -> str:
    lower = url.lower().split("?", 1)[0]
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


def _frontend_products(item: dict[str, Any], preview_url: str) -> list[dict[str, Any]]:
    """Preserve the provider original and normalize the UI manifest's camelCase products."""
    products: list[dict[str, Any]] = []
    original_url = str(item.get("originalUrl") or item.get("original_url") or "")
    if original_url:
        products.append(
            {
                "url": original_url,
                "subtype": "provider_original",
                "media_type": _image_type(original_url),
                "is_original": True,
            }
        )
    for product in item.get("products") or []:
        if not isinstance(product, dict) or not product.get("url"):
            continue
        url = str(product["url"])
        if url == original_url:
            continue
        products.append(
            {
                "url": url,
                "subtype": str(product.get("kind") or product.get("subtype") or "source"),
                "media_type": str(
                    product.get("mediaType") or product.get("media_type") or _image_type(url)
                ),
                "byte_size": product.get("byteSize") or product.get("byte_size"),
                "data_level": product.get("dataLevel") or product.get("data_level"),
                "is_original": bool(product.get("isOriginal", product.get("is_original", False))),
            }
        )
    if not products and preview_url:
        products.append(
            {
                "url": preview_url,
                "subtype": "official_rendition",
                "media_type": _image_type(preview_url),
                "is_original": True,
            }
        )
    return products


def _member_key(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("slug") or value.get("id") or value.get("url") or "")
    return str(value)
