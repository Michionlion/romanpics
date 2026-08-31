from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from .base import (
    NormalizedProduct,
    NormalizedRecord,
    NormalizedRendition,
    SourceAdapter,
    SourcePage,
)
from .common import clean_text, content_type_from_url, parse_datetime, slugify


class NasaImagesAdapter(SourceAdapter):
    name = "nasa_images"
    display_name = "NASA Image and Video Library"
    canonical_host = "images.nasa.gov"
    terms_url = "https://www.nasa.gov/nasa-brand-center/images-and-media/"
    search_queries = ("Roman Space Telescope", "Nancy Grace Roman", "WFIRST")

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def discover(
        self, cursor: str | None = None, modified_since: datetime | None = None
    ) -> SourcePage:
        try:
            query_index, page = (int(part) for part in (cursor or "0:1").split(":"))
            query = self.search_queries[query_index]
        except (ValueError, IndexError):
            raise ValueError("invalid NASA Images adapter cursor") from None
        page = max(1, page)
        params: dict[str, object] = {
            "q": query,
            "media_type": "image",
            "page": page,
            "page_size": 100,
        }
        if modified_since:
            params["year_start"] = modified_since.year
        response = await self.client.get("https://images-api.nasa.gov/search", params=params)
        response.raise_for_status()
        collection = response.json().get("collection", {})
        records = list(collection.get("items", []))
        total = int(collection.get("metadata", {}).get("total_hits", len(records)))
        if page * 100 < total and records:
            next_cursor = f"{query_index}:{page + 1}"
        elif query_index + 1 < len(self.search_queries):
            next_cursor = f"{query_index + 1}:1"
        else:
            next_cursor = None
        return SourcePage(records=records, next_cursor=next_cursor)

    async def normalize(self, record: dict[str, Any]) -> NormalizedRecord:
        data = (record.get("data") or [{}])[0]
        external_id = str(data.get("nasa_id") or "").strip()
        title = clean_text(data.get("title"), "Untitled NASA image")
        if not external_id:
            raise ValueError("NASA Images record has no nasa_id")

        assets_payload = record.get("asset_manifest")
        if assets_payload is None:
            response = await self.client.get(f"https://images-api.nasa.gov/asset/{external_id}")
            response.raise_for_status()
            assets_payload = response.json()
        asset_urls = [
            _upgrade_asset_url(str(item.get("href")))
            for item in assets_payload.get("collection", {}).get("items", [])
            if item.get("href")
        ]
        links = record.get("links") or []
        preview_url = next(
            (
                _upgrade_asset_url(str(link["href"]))
                for link in links
                if link.get("href") and link.get("render") == "image"
            ),
            None,
        )
        if not preview_url:
            preview_url = next((url for url in asset_urls if "~medium" in url), None)
        if not preview_url:
            preview_url = next(
                (url for url in asset_urls if content_type_from_url(url).startswith("image/")), None
            )
        if not preview_url:
            raise ValueError(f"NASA Images record {external_id} has no image rendition")

        original_url = next(
            (url for url in asset_urls if "~orig" in url or "~original" in url),
            asset_urls[-1] if asset_urls else preview_url,
        )
        description = clean_text(
            data.get("description_508") or data.get("description"),
            f"NASA image related to the Nancy Grace Roman Space Telescope: {title}.",
        )
        keywords = [clean_text(item) for item in data.get("keywords", []) if clean_text(item)]
        content_class = _classify(data, keywords)
        credit = clean_text(data.get("secondary_creator") or data.get("photographer"), "NASA")
        published = parse_datetime(data.get("date_created"))
        return NormalizedRecord(
            external_id=external_id,
            canonical_url=f"https://images.nasa.gov/details/{external_id}",
            slug=slugify(title),
            title=title,
            summary=description,
            content_class=content_class,
            is_flight_data=False,
            alt_text=description,
            credit=credit,
            raw={"search": record, "asset_manifest": assets_payload},
            published_at=published,
            upstream_created_at=published,
            rights="See NASA media usage guidelines and item-specific credits.",
            rights_url=self.terms_url,
            tags=keywords,
            products=[
                NormalizedProduct(
                    url=original_url,
                    subtype="original",
                    media_type=content_type_from_url(original_url),
                    is_original=True,
                )
            ],
            renditions=[
                NormalizedRendition(
                    url=preview_url,
                    width=1024,
                    height=1024,
                    format=content_type_from_url(preview_url),
                    provider="NASA_IMAGES",
                    alt_text=description,
                    credit=credit,
                    rights="See NASA media usage guidelines and item-specific credits.",
                    rights_url=self.terms_url,
                )
            ],
            metadata={"center": data.get("center"), "location": data.get("location")},
        )


def _classify(data: dict[str, Any], keywords: list[str]) -> str:
    text = " ".join(
        [str(data.get("title", "")), str(data.get("description", "")), *keywords]
    ).lower()
    if any(word in text for word in ("illustration", "artist", "visualization", "concept")):
        return "VISUALIZATION"
    if any(word in text for word in ("test data", "detector test", "ground test")):
        return "GROUND_TEST"
    return "MISSION_PHOTO"


def _upgrade_asset_url(url: str) -> str:
    prefix = "http://images-assets.nasa.gov/"
    if url.startswith(prefix):
        return f"https://images-assets.nasa.gov/{url.removeprefix(prefix)}"
    return url
