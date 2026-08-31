from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class SourcePage:
    records: list[dict[str, Any]]
    next_cursor: str | None = None


@dataclass(slots=True)
class NormalizedObservation:
    observation_id: str
    mission: str = "Roman"
    program_id: str | None = None
    survey: str | None = None
    instrument: str | None = None
    mode: str | None = None
    optical_elements: list[str] = field(default_factory=list)
    target: str | None = None
    ra: float | None = None
    dec: float | None = None
    observed_start: datetime | None = None
    observed_end: datetime | None = None
    data_level: str | None = None
    product_version: str | None = None
    pipeline_version: str | None = None
    release_name: str | None = None


@dataclass(slots=True)
class NormalizedProduct:
    url: str
    subtype: str
    media_type: str
    byte_size: int | None = None
    is_original: bool = False
    data_level: str | None = None


@dataclass(slots=True)
class NormalizedRendition:
    url: str
    width: int
    height: int
    format: str
    provider: str
    alt_text: str
    credit: str
    rights: str | None = None
    rights_url: str | None = None
    site_generated: bool = False
    transformation: str | None = None
    role: str = "preview"


@dataclass(slots=True)
class NormalizedRecord:
    external_id: str
    canonical_url: str
    slug: str
    title: str
    summary: str
    content_class: str
    is_flight_data: bool
    alt_text: str
    credit: str
    raw: dict[str, Any]
    published_at: datetime | None = None
    upstream_created_at: datetime | None = None
    upstream_updated_at: datetime | None = None
    etag: str | None = None
    rights: str | None = None
    rights_url: str | None = None
    processing_note: str | None = None
    tags: list[str] = field(default_factory=list)
    observation: NormalizedObservation | None = None
    products: list[NormalizedProduct] = field(default_factory=list)
    renditions: list[NormalizedRendition] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    supersedes_external_id: str | None = None


class SourceAdapter(ABC):
    name: str
    display_name: str
    canonical_host: str
    terms_url: str | None = None

    @abstractmethod
    async def discover(
        self, cursor: str | None = None, modified_since: datetime | None = None
    ) -> SourcePage:
        """Return one page without leaking its schema past the adapter."""

    @abstractmethod
    async def normalize(self, record: dict[str, Any]) -> NormalizedRecord:
        """Validate and map one provider record."""
