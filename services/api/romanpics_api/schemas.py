from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ContentClass(StrEnum):
    FLIGHT_SCIENCE = "FLIGHT_SCIENCE"
    SIMULATION = "SIMULATION"
    GROUND_TEST = "GROUND_TEST"
    MISSION_PHOTO = "MISSION_PHOTO"
    VISUALIZATION = "VISUALIZATION"


class SourceOut(BaseModel):
    provider: str
    external_id: str
    source_url: str
    archive_record_url: str | None = None
    credit: str
    rights: str | None = None
    rights_url: str | None = None


class RenditionOut(BaseModel):
    url: str
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    format: str
    provider: str
    site_generated: bool
    transformation: str | None = None


class ObservationOut(BaseModel):
    observation_id: str
    program_id: str | None = None
    survey: str | None = None
    instrument: str | None = None
    mode: str | None = None
    optical_elements: list[str] = []
    target: str | None = None
    ra: float | None = None
    dec: float | None = None
    data_level: str | None = None
    release_name: str | None = None
    pipeline_version: str | None = None


class ArchiveProductOut(BaseModel):
    id: str
    url: str
    subtype: str
    media_type: str
    byte_size: int | None = Field(default=None, ge=0)
    data_level: str | None = None
    active: bool
    superseded_by: str | None = None


class GalleryItemOut(BaseModel):
    id: str
    slug: str
    title: str
    summary: str
    content_class: ContentClass
    is_flight_data: bool
    published_at: datetime | None = None
    observed_at: datetime | None = None
    source: SourceOut
    preview: RenditionOut
    alt_text: str
    tags: list[str]
    vote_count: int = Field(ge=0)
    viewer_has_voted: bool = False
    cluster_id: str | None = None


class ItemDetailOut(GalleryItemOut):
    originals: list[ArchiveProductOut]
    observation: ObservationOut | None
    processing_note: str | None = None
    superseded_by: str | None = None


class ItemPage(BaseModel):
    data: list[GalleryItemOut]
    next_cursor: str | None = None
    total_estimate: int = Field(ge=0)


class SimilarItemOut(BaseModel):
    item: GalleryItemOut
    score: float = Field(ge=0, le=1)
    reasons: list[Literal["same_observation", "same_target", "duplicate", "visual", "metadata"]]


class SimilarPage(BaseModel):
    data: list[SimilarItemOut]
    algorithm_version: str


class ProductPage(BaseModel):
    data: list[ArchiveProductOut]
    next_cursor: str | None = None


class ClusterOut(BaseModel):
    id: str
    slug: str
    title: str
    summary: str
    content_class: ContentClass
    representative: GalleryItemOut
    item_count: int = Field(ge=1)
    vote_count: int = Field(ge=0)
    viewer_has_voted: bool = False
    version: str
    archived_at: datetime | None = None


class ClusterDetailOut(ClusterOut):
    members: list[GalleryItemOut]
    next_cursor: str | None = None


class ClusterPage(BaseModel):
    data: list[ClusterOut]
    next_cursor: str | None = None
    total_estimate: int = Field(ge=0)


class CollectionOut(BaseModel):
    slug: str
    title: str
    summary: str
    items: list[GalleryItemOut]


class CollectionSummaryOut(BaseModel):
    slug: str
    title: str
    summary: str
    item_count: int = Field(ge=0)
    updated_at: datetime


class CollectionPage(BaseModel):
    data: list[CollectionSummaryOut]


class Suggestion(BaseModel):
    kind: Literal["item", "target", "tag", "survey"]
    label: str
    value: str


class SuggestionPage(BaseModel):
    data: list[Suggestion]


class FacetValue(BaseModel):
    value: str
    count: int = Field(ge=0)


class FacetPage(BaseModel):
    model_config = ConfigDict(extra="allow")

    content_class: list[FacetValue] = []
    instrument: list[FacetValue] = []
    survey: list[FacetValue] = []
    optical_element: list[FacetValue] = []
    target: list[FacetValue] = []
    tag: list[FacetValue] = []


class SourceStatusOut(BaseModel):
    adapter: str
    state: Literal["healthy", "delayed", "degraded"]
    last_success_at: datetime | None
    last_error_at: datetime | None = None
    public_message: str | None = None
    record_count: int = Field(ge=0)


class SourceStatusPage(BaseModel):
    data: list[SourceStatusOut]
    generated_at: datetime


class VoteState(BaseModel):
    target_kind: Literal["item", "cluster"]
    target_id: str
    viewer_has_voted: bool
    vote_count: int = Field(ge=0)


class SurpriseOut(BaseModel):
    mode: Literal["anything", "galaxies", "mission", "calm", "engineering"]
    item: GalleryItemOut


class Problem(BaseModel):
    type: str
    title: str
    status: int = Field(ge=400, le=599)
    detail: str | None = None
    instance: str | None = None
    errors: list[dict[str, Any]] | None = None
