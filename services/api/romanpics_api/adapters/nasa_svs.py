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


class NasaSvsAdapter(SourceAdapter):
    name = "nasa_svs"
    display_name = "NASA Scientific Visualization Studio"
    canonical_host = "svs.gsfc.nasa.gov"
    terms_url = "https://www.nasa.gov/nasa-brand-center/images-and-media/"

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def discover(
        self, cursor: str | None = None, modified_since: datetime | None = None
    ) -> SourcePage:
        page = max(1, int(cursor or 1))
        response = await self.client.get(
            "https://svs.gsfc.nasa.gov/api/search/", params={"search": "Roman", "page": page}
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            records = payload
            next_cursor = None
        else:
            records = list(payload.get("results") or payload.get("items") or [])
            next_cursor = str(page + 1) if payload.get("next") else None
        return SourcePage(records=records, next_cursor=next_cursor)

    async def normalize(self, record: dict[str, Any]) -> NormalizedRecord:
        external_id = str(record.get("id") or record.get("svs_id") or "").strip()
        if not external_id:
            raise ValueError("SVS record has no id")
        detail = record.get("detail")
        if not detail:
            response = await self.client.get(f"https://svs.gsfc.nasa.gov/api/{external_id}/")
            response.raise_for_status()
            detail = response.json()
        if not isinstance(detail, dict):
            raise ValueError(f"SVS detail for {external_id} is not an object")

        title = clean_text(detail.get("title") or record.get("title"), "Untitled SVS item")
        description = clean_text(
            detail.get("description") or detail.get("summary"),
            f"NASA visualization related to Roman: {title}.",
        )
        credit = _credit(detail)
        media = _media(detail)
        main_image = detail.get("main_image")
        if isinstance(main_image, dict):
            main_url = main_image.get("url") or main_image.get("href")
            width = int(main_image.get("width") or 1280)
            height = int(main_image.get("height") or 720)
            main_alt_text = main_image.get("alt_text") or main_image.get("alttext")
        else:
            main_url = main_image
            main_alt_text = None
            size = detail.get("main_image_size") or [1280, 720]
            width = int(size[0]) if isinstance(size, list) and size else 1280
            height = int(size[1]) if isinstance(size, list) and len(size) > 1 else 720
        candidates = [
            item
            for item in media
            if str(item.get("url", ""))
            .lower()
            .split("?", 1)[0]
            .endswith((".jpg", ".jpeg", ".png", ".webp"))
        ]
        preview = next(
            (item for item in candidates if "_searchweb" in str(item.get("url", "")).lower()),
            candidates[0] if candidates else None,
        )
        preview_url = str((preview or {}).get("url") or main_url or "")
        if not preview_url:
            raise ValueError(f"SVS record {external_id} has no browser image")
        alt_text = clean_text(
            detail.get("alt_text")
            or detail.get("alttext")
            or main_alt_text
            or (preview or {}).get("alt_text")
            or (preview or {}).get("alttext")
            or description,
            description,
        )
        width = int((preview or {}).get("width") or width or 1)
        height = int((preview or {}).get("height") or height or 1)
        page_url = str(
            detail.get("page_url")
            or detail.get("url")
            or f"https://svs.gsfc.nasa.gov/{external_id}/"
        )
        published = parse_datetime(
            detail.get("release_date") or detail.get("date") or detail.get("published")
        )
        updated = parse_datetime(detail.get("update_date"))
        content_class = _classify(detail)
        tags = [
            clean_text(tag)
            for tag in (detail.get("keywords") or detail.get("tags") or [])
            if clean_text(tag)
        ]
        original_url = str(main_url or preview_url)
        return NormalizedRecord(
            external_id=external_id,
            canonical_url=page_url,
            slug=slugify(title),
            title=title,
            summary=description,
            content_class=content_class,
            is_flight_data=False,
            alt_text=alt_text,
            credit=credit,
            raw={"search": record, "detail": detail},
            published_at=published,
            upstream_created_at=published,
            upstream_updated_at=updated,
            rights="See item credits and NASA media usage guidelines.",
            rights_url=self.terms_url,
            tags=tags,
            products=[
                NormalizedProduct(
                    url=original_url,
                    subtype="source_still",
                    media_type=content_type_from_url(original_url),
                    is_original=True,
                )
            ],
            renditions=[
                NormalizedRendition(
                    url=preview_url,
                    width=max(1, width),
                    height=max(1, height),
                    format=content_type_from_url(preview_url),
                    provider="NASA_SVS",
                    alt_text=alt_text,
                    credit=credit,
                    rights="See item credits and NASA media usage guidelines.",
                    rights_url=self.terms_url,
                )
            ],
            metadata={"svs_type": detail.get("page_type") or detail.get("type")},
        )


def _media(detail: dict[str, Any]) -> list[dict[str, Any]]:
    groups = detail.get("media_groups") or []
    nested: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        for item in group.get("items") or []:
            if not isinstance(item, dict):
                continue
            instances = item.get("instance") or item.get("instances") or []
            if isinstance(instances, dict):
                instances = [instances]
            for instance in instances:
                if isinstance(instance, dict):
                    nested.append(instance)
    if nested:
        return nested
    value = detail.get("media") or detail.get("files") or []
    if isinstance(value, dict):
        flattened: list[dict[str, Any]] = []
        for items in value.values():
            if isinstance(items, list):
                flattened.extend(item for item in items if isinstance(item, dict))
        return flattened
    return [item for item in value if isinstance(item, dict)]


def _credit(detail: dict[str, Any]) -> str:
    value = detail.get("credits") or detail.get("credit")
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                people = item.get("people") or []
                if people:
                    parts.extend(
                        clean_text(person.get("name"))
                        for person in people
                        if isinstance(person, dict) and person.get("name")
                    )
                else:
                    parts.append(clean_text(item.get("name") or item.get("credit")))
            else:
                parts.append(clean_text(item))
        return " / ".join(part for part in parts if part) or "NASA GSFC"
    return clean_text(value, "NASA GSFC")


def _classify(detail: dict[str, Any]) -> str:
    text = " ".join(
        str(detail.get(key, ""))
        for key in ("title", "description", "page_type", "type", "keywords")
    ).lower()
    if "simulat" in text or "synthetic" in text:
        return "SIMULATION"
    if any(term in text for term in ("cleanroom", "technician", "hardware", "test")):
        return "GROUND_TEST"
    return "VISUALIZATION"
