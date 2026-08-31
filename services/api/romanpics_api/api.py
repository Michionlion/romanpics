from __future__ import annotations

import hashlib
import json
import random
import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .config import Settings
from .models import (
    Cluster,
    ClusterMember,
    Collection,
    GalleryItem,
    ItemTag,
    Observation,
    Tag,
)
from .schemas import (
    ClusterDetailOut,
    ClusterPage,
    CollectionOut,
    CollectionPage,
    CollectionSummaryOut,
    ContentClass,
    FacetPage,
    FacetValue,
    ItemDetailOut,
    ItemPage,
    ProductPage,
    SimilarItemOut,
    SimilarPage,
    SourceStatusPage,
    Suggestion,
    SuggestionPage,
    SurpriseOut,
    VoteState,
)
from .services.catalog import (
    apply_item_sort,
    collection_items,
    get_item_row,
    item_query,
    products_for_item,
    serialize_cluster,
    serialize_item,
    serialize_item_detail,
    serialize_product,
    similarity_rows,
    within_cone,
)
from .services.ingestion import source_status
from .services.security import (
    daily_network_hmac,
    decode_cursor,
    encode_cursor,
    new_actor,
    read_visitor,
    sign_visitor,
)
from .services.votes import set_vote, target_exists

router = APIRouter(prefix="/v1")
Limit = Annotated[int, Query(ge=1, le=100)]


def get_session(request: Request):
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_actor(request: Request) -> str | None:
    settings: Settings = request.app.state.settings
    return read_visitor(request.cookies.get(settings.cookie_name), settings.visitor_signing_secret)


@router.get("/items", response_model=ItemPage, operation_id="listItems")
def list_items(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    actor_id: Annotated[str | None, Depends(get_actor)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    content_class: ContentClass | None = None,
    flight_only: bool | None = None,
    instrument: str | None = None,
    survey: str | None = None,
    optical_element: str | None = None,
    target: str | None = None,
    tag: str | None = None,
    published_from: date | None = None,
    published_to: date | None = None,
    ra: Annotated[float | None, Query(ge=0, le=360)] = None,
    dec: Annotated[float | None, Query(ge=-90, le=90)] = None,
    radius: Annotated[float | None, Query(gt=0, le=10)] = None,
    cluster: str | None = None,
    sort: Literal["top", "trending", "newest", "relevance"] = "newest",
    cursor: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    limit: Limit = 24,
) -> ItemPage:
    cone = (ra, dec, radius)
    if any(value is not None for value in cone) and not all(value is not None for value in cone):
        raise HTTPException(400, "ra, dec, and radius must be supplied together")
    if cursor and page is not None:
        raise HTTPException(400, "cursor and page cannot be supplied together")
    try:
        offset = (page - 1) * limit if page is not None else decode_cursor(cursor)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    statement = item_query(
        q=q,
        content_class=content_class.value if content_class else None,
        flight_only=flight_only,
        instrument=instrument,
        survey=survey,
        optical_element=optical_element,
        target=target,
        tag=tag,
        published_from=published_from,
        published_to=published_to,
        cluster=cluster,
    )
    statement = apply_item_sort(statement, sort, q)
    if ra is not None and dec is not None and radius is not None:
        candidates = list(session.scalars(statement).unique().all())
        candidates = [item for item in candidates if within_cone(item, session, ra, dec, radius)]
        total = len(candidates)
        page_rows = candidates[offset : offset + limit]
    else:
        total = (
            session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
            or 0
        )
        page_rows = list(session.scalars(statement.offset(offset).limit(limit)).unique().all())
    page = ItemPage(
        data=[serialize_item(session, row, actor_id) for row in page_rows],
        next_cursor=encode_cursor(offset + limit) if offset + limit < total else None,
        total_estimate=total,
    )
    _cache_read(request, response, page, max_age=60)
    return page


@router.get("/items/{item}", response_model=ItemDetailOut, operation_id="getItem")
def get_item(
    item: str,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    actor_id: Annotated[str | None, Depends(get_actor)],
) -> ItemDetailOut:
    row = get_item_row(session, item)
    if row is None:
        raise HTTPException(404, "gallery item not found")
    result = serialize_item_detail(session, row, actor_id)
    _cache_read(request, response, result, max_age=300)
    return result


@router.get("/items/{item}/similar", response_model=SimilarPage, operation_id="listSimilarItems")
def list_similar_items(
    item: str,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    actor_id: Annotated[str | None, Depends(get_actor)],
    limit: Limit = 24,
) -> SimilarPage:
    row = get_item_row(session, item)
    if row is None:
        raise HTTPException(404, "gallery item not found")
    edges = similarity_rows(session, row.id, limit)
    versions = {edge.algorithm_version for edge in edges}
    version = sorted(versions)[-1] if versions else "none"
    result = SimilarPage(
        data=[
            SimilarItemOut(
                item=serialize_item(
                    session, session.get(GalleryItem, edge.related_item_id), actor_id
                ),
                score=edge.score,
                reasons=edge.reasons,
            )
            for edge in edges
            if session.get(GalleryItem, edge.related_item_id) is not None
        ],
        algorithm_version=version,
    )
    _cache_read(request, response, result, max_age=300)
    return result


@router.get("/items/{item}/products", response_model=ProductPage, operation_id="listItemProducts")
def list_item_products(
    item: str,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    cursor: str | None = None,
    limit: Limit = 24,
) -> ProductPage:
    row = get_item_row(session, item)
    if row is None:
        raise HTTPException(404, "gallery item not found")
    try:
        offset = decode_cursor(cursor)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    products = products_for_item(session, row.id)
    page = products[offset : offset + limit]
    result = ProductPage(
        data=[serialize_product(product) for product in page],
        next_cursor=encode_cursor(offset + limit) if offset + limit < len(products) else None,
    )
    _cache_read(request, response, result, max_age=300)
    return result


@router.get("/clusters", response_model=ClusterPage, operation_id="listClusters")
def list_clusters(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    actor_id: Annotated[str | None, Depends(get_actor)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    content_class: ContentClass | None = None,
    sort: Literal["top", "trending", "newest"] = "top",
    cursor: str | None = None,
    limit: Limit = 24,
) -> ClusterPage:
    try:
        offset = decode_cursor(cursor)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    statement = select(Cluster).where(Cluster.archived_at.is_(None))
    if q:
        statement = statement.where(
            or_(Cluster.title.ilike(f"%{q}%"), Cluster.summary.ilike(f"%{q}%"))
        )
    if content_class:
        statement = statement.where(Cluster.content_class == content_class.value)
    # serialize_cluster obtains exact totals. The initial fixture is small, so
    # sorting in memory keeps SQLite/PostgreSQL behavior identical.
    clusters = list(session.scalars(statement).all())
    serialized = [serialize_cluster(session, row, actor_id) for row in clusters]
    if sort in {"top", "trending"}:
        serialized.sort(key=lambda row: (row.vote_count, row.title), reverse=True)
    else:
        serialized.sort(key=lambda row: row.title)
    total = len(serialized)
    result = ClusterPage(
        data=serialized[offset : offset + limit],
        next_cursor=encode_cursor(offset + limit) if offset + limit < total else None,
        total_estimate=total,
    )
    _cache_read(request, response, result, max_age=60)
    return result


@router.get("/clusters/{cluster}", response_model=ClusterDetailOut, operation_id="getCluster")
def get_cluster(
    cluster: str,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    actor_id: Annotated[str | None, Depends(get_actor)],
    cursor: str | None = None,
    limit: Limit = 24,
) -> ClusterDetailOut:
    row = session.scalar(select(Cluster).where(or_(Cluster.id == cluster, Cluster.slug == cluster)))
    if row is None:
        raise HTTPException(404, "cluster not found")
    try:
        offset = decode_cursor(cursor)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    members = list(
        session.scalars(
            select(GalleryItem)
            .join(ClusterMember, ClusterMember.item_id == GalleryItem.id)
            .where(ClusterMember.cluster_id == row.id)
            .order_by(ClusterMember.rank)
        ).all()
    )
    base = serialize_cluster(session, row, actor_id).model_dump()
    result = ClusterDetailOut(
        **base,
        members=[
            serialize_item(session, item, actor_id) for item in members[offset : offset + limit]
        ],
        next_cursor=encode_cursor(offset + limit) if offset + limit < len(members) else None,
    )
    _cache_read(request, response, result, max_age=120)
    return result


@router.get("/collections", response_model=CollectionPage, operation_id="listCollections")
def list_collections(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> CollectionPage:
    rows = list(
        session.scalars(
            select(Collection).where(Collection.published.is_(True)).order_by(Collection.title)
        ).all()
    )
    result = CollectionPage(
        data=[
            CollectionSummaryOut(
                slug=row.slug,
                title=row.title,
                summary=row.summary,
                item_count=len(collection_items(session, row)),
                updated_at=row.updated_at,
            )
            for row in rows
        ]
    )
    _cache_read(request, response, result, max_age=300)
    return result


@router.get("/collections/{slug}", response_model=CollectionOut, operation_id="getCollection")
def get_collection(
    slug: str,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    actor_id: Annotated[str | None, Depends(get_actor)],
) -> CollectionOut:
    row = session.scalar(
        select(Collection).where(Collection.slug == slug, Collection.published.is_(True))
    )
    if row is None:
        raise HTTPException(404, "collection not found")
    result = CollectionOut(
        slug=row.slug,
        title=row.title,
        summary=row.summary,
        items=[serialize_item(session, item, actor_id) for item in collection_items(session, row)],
    )
    _cache_read(request, response, result, max_age=300)
    return result


@router.get("/search/suggest", response_model=SuggestionPage, operation_id="suggestSearch")
def search_suggest(
    q: Annotated[str, Query(min_length=2, max_length=100)],
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> SuggestionPage:
    pattern = f"%{q}%"
    data: list[Suggestion] = []
    for item in session.scalars(
        select(GalleryItem)
        .where(
            GalleryItem.editorial_state == "published",
            or_(GalleryItem.title.ilike(pattern), GalleryItem.search_document.ilike(pattern)),
        )
        .limit(5)
    ):
        data.append(Suggestion(kind="item", label=item.title, value=item.slug))
    for tag in session.scalars(select(Tag).where(Tag.label.ilike(pattern)).limit(4)):
        data.append(Suggestion(kind="tag", label=tag.label, value=tag.slug))
    for target in session.scalars(
        select(Observation.target_name)
        .where(Observation.target_name.ilike(pattern))
        .distinct()
        .limit(3)
    ):
        data.append(Suggestion(kind="target", label=target, value=target))
    result = SuggestionPage(data=data[:12])
    _cache_read(request, response, result, max_age=60)
    return result


@router.get("/facets", response_model=FacetPage, operation_id="getFacets")
def get_facets(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> FacetPage:
    items = list(session.scalars(item_query(q=q)).unique().all())
    ids = [item.id for item in items]
    observations = [
        session.get(Observation, item.primary_observation_id)
        for item in items
        if item.primary_observation_id
    ]
    tag_rows = session.execute(
        select(Tag.label, func.count(Tag.id))
        .join_from(Tag, ItemTag)
        .where(ItemTag.item_id.in_(ids or ["-"]))
        .group_by(Tag.label)
    ).all()
    result = FacetPage(
        content_class=_counts(item.content_class for item in items),
        instrument=_counts(obs.instrument for obs in observations if obs and obs.instrument),
        survey=_counts(obs.survey for obs in observations if obs and obs.survey),
        optical_element=_counts(
            element for obs in observations if obs for element in obs.optical_elements
        ),
        target=_counts(obs.target_name for obs in observations if obs and obs.target_name),
        tag=[FacetValue(value=label, count=count) for label, count in tag_rows],
    )
    _cache_read(request, response, result, max_age=60)
    return result


@router.get("/sources/status", response_model=SourceStatusPage, operation_id="listSourceStatus")
def list_source_status(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> SourceStatusPage:
    result = SourceStatusPage(data=source_status(session), generated_at=datetime.now(UTC))
    _cache_read(request, response, result, max_age=30)
    return result


@router.get("/surprise", response_model=SurpriseOut, operation_id="getSurprise")
def get_surprise(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    actor_id: Annotated[str | None, Depends(get_actor)],
    mode: Literal["anything", "galaxies", "mission", "calm", "engineering"] = "anything",
) -> SurpriseOut:
    statement = item_query()
    if mode == "galaxies":
        statement = statement.where(GalleryItem.search_document.ilike("%galax%"))
    elif mode == "mission":
        statement = statement.where(GalleryItem.content_class.in_(["MISSION_PHOTO", "GROUND_TEST"]))
    elif mode == "engineering":
        statement = statement.where(
            or_(
                GalleryItem.search_document.ilike("%engineering%"),
                GalleryItem.search_document.ilike("%hardware%"),
                GalleryItem.search_document.ilike("%cleanroom%"),
            )
        )
    elif mode == "calm":
        statement = statement.where(GalleryItem.content_class.in_(["SIMULATION", "VISUALIZATION"]))
    ids = list(session.scalars(statement.with_only_columns(GalleryItem.id)).all())
    if not ids:
        raise HTTPException(404, f"no items are available for surprise mode {mode}")
    row = session.get(GalleryItem, random.SystemRandom().choice(ids))
    response.headers["Cache-Control"] = "private, no-store"
    return SurpriseOut(mode=mode, item=serialize_item(session, row, actor_id))


@router.put("/me/votes/items/{id}", response_model=VoteState, operation_id="addItemVote")
def add_item_vote(
    id: uuid.UUID,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> VoteState:
    return _vote(request, response, session, "item", str(id), True)


@router.delete("/me/votes/items/{id}", response_model=VoteState, operation_id="removeItemVote")
def remove_item_vote(
    id: uuid.UUID,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> VoteState:
    return _vote(request, response, session, "item", str(id), False)


@router.put("/me/votes/clusters/{id}", response_model=VoteState, operation_id="addClusterVote")
def add_cluster_vote(
    id: uuid.UUID,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> VoteState:
    return _vote(request, response, session, "cluster", str(id), True)


@router.delete(
    "/me/votes/clusters/{id}", response_model=VoteState, operation_id="removeClusterVote"
)
def remove_cluster_vote(
    id: uuid.UUID,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> VoteState:
    return _vote(request, response, session, "cluster", str(id), False)


def _vote(
    request: Request,
    response: Response,
    session: Session,
    kind: Literal["item", "cluster"],
    target_id: str,
    enabled: bool,
) -> VoteState:
    settings: Settings = request.app.state.settings
    actor_id = (
        read_visitor(request.cookies.get(settings.cookie_name), settings.visitor_signing_secret)
        or new_actor()
    )
    network_key = daily_network_hmac(
        request.client.host if request.client else None, settings.visitor_signing_secret
    )
    limiter = request.app.state.vote_limiter
    actor_allowed = limiter.allow(f"actor:{actor_id}")
    network_allowed = network_key is None or limiter.allow(f"network:{network_key}")
    if not actor_allowed or not network_allowed:
        raise HTTPException(429, "vote rate limit exceeded")
    if not target_exists(session, kind, target_id):
        raise HTTPException(404, f"{kind} not found")
    voted, count = set_vote(
        session,
        actor_id=actor_id,
        kind=kind,
        target_id=target_id,
        enabled=enabled,
        network_hmac=network_key,
    )
    response.set_cookie(
        settings.cookie_name,
        sign_visitor(actor_id, settings.visitor_signing_secret),
        max_age=settings.cookie_max_age_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    response.headers["Cache-Control"] = "private, no-store"
    return VoteState(
        target_kind=kind,
        target_id=target_id,
        viewer_has_voted=voted,
        vote_count=count,
    )


def _counts(values) -> list[FacetValue]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return [
        FacetValue(value=value, count=count)
        for value, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]


def _cache_read(request: Request, response: Response, value: object, *, max_age: int) -> None:
    payload_value = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    payload = json.dumps(payload_value, sort_keys=True, separators=(",", ":"), default=str)
    etag = f'"{hashlib.sha256(payload.encode()).hexdigest()}"'
    response.headers["ETag"] = etag
    settings: Settings = request.app.state.settings
    if settings.cookie_name in request.cookies:
        response.headers["Cache-Control"] = "private, no-cache"
        response.headers["Vary"] = _append_vary(response.headers.get("Vary"), "Cookie")
    else:
        response.headers["Cache-Control"] = (
            f"public, max-age={max_age}, stale-while-revalidate={max_age * 5}"
        )
    candidates = {token.strip() for token in request.headers.get("if-none-match", "").split(",")}
    if etag in candidates or "*" in candidates:
        response.status_code = 304


def _append_vary(current: str | None, value: str) -> str:
    values = {part.strip() for part in (current or "").split(",") if part.strip()}
    values.add(value)
    return ", ".join(sorted(values))
