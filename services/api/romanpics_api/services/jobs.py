from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import Job, stable_uuid, utcnow


def enqueue_job(
    session: Session,
    *,
    job_type: str,
    payload_json: dict[str, object],
    dedupe_key: str | None = None,
    priority: int = 0,
    max_attempts: int = 5,
    available_at: datetime | None = None,
) -> tuple[Job, bool]:
    """Create a queue row once; callers commit with their catalog transaction."""
    if dedupe_key:
        existing = session.scalar(select(Job).where(Job.dedupe_key == dedupe_key))
        if existing is not None:
            return existing, False
    job = Job(
        id=stable_uuid("job", dedupe_key) if dedupe_key else None,
        job_type=job_type,
        payload_json=payload_json,
        priority=priority,
        max_attempts=max_attempts,
        available_at=available_at or utcnow(),
        dedupe_key=dedupe_key,
    )
    # Passing None bypasses SQLAlchemy's Python default on some dialects.
    if job.id is None:
        from ..models import new_uuid

        job.id = new_uuid()
    session.add(job)
    return job, True


def enqueue_embed(
    session: Session, *, item_id: str, source_record_id: str, checksum: str
) -> tuple[Job, bool]:
    return enqueue_job(
        session,
        job_type="embed",
        payload_json={
            "item_id": item_id,
            "source_record_id": source_record_id,
            "checksum": checksum,
        },
        dedupe_key=f"embed:{item_id}:{checksum}",
        priority=10,
    )


def enqueue_cluster_refresh(
    session: Session, *, source_id: str, ingest_run_id: str
) -> tuple[Job, bool]:
    return enqueue_job(
        session,
        job_type="cluster",
        payload_json={"source_id": source_id, "ingest_run_id": ingest_run_id},
        dedupe_key=f"cluster:{ingest_run_id}",
    )


def enqueue_render(
    session: Session,
    *,
    item_id: str,
    product_id: str,
    recipe: dict[str, object],
    source_checksum: str | None = None,
) -> tuple[Job, bool]:
    return enqueue_job(
        session,
        job_type="render",
        payload_json={"item_id": item_id, "product_id": product_id, "recipe": recipe},
        dedupe_key=(
            f"render:{item_id}:{product_id}:{recipe.get('version', 'v1')}"
            f":{source_checksum or 'unknown'}"
        ),
        priority=20,
    )


def enqueue_link_check(session: Session, *, scope: str = "catalog") -> tuple[Job, bool]:
    day = utcnow().date().isoformat()
    return enqueue_job(
        session,
        job_type="link-check",
        payload_json={"scope": scope},
        dedupe_key=f"link-check:{scope}:{day}",
        priority=-10,
    )


def retry_failed_jobs(
    session: Session, *, job_type: str | None = None, limit: int = 100
) -> list[str]:
    """Reset a bounded failed-job batch while retaining its dedupe identity."""
    if job_type is not None and job_type not in {"render", "embed", "cluster", "link-check"}:
        raise ValueError(f"unsupported job type: {job_type}")
    if not 1 <= limit <= 1_000:
        raise ValueError("limit must be between 1 and 1000")
    statement = select(Job.id).where(Job.status == "failed").order_by(Job.updated_at, Job.id)
    if job_type is not None:
        statement = statement.where(Job.job_type == job_type)
    identifiers = list(session.scalars(statement.limit(limit)))
    if not identifiers:
        return []
    session.execute(
        update(Job)
        .where(Job.id.in_(identifiers), Job.status == "failed")
        .values(
            status="queued",
            attempts=0,
            available_at=utcnow(),
            locked_by=None,
            locked_at=None,
            result_json=None,
            error=None,
            updated_at=utcnow(),
        )
    )
    return identifiers
