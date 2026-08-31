from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import delete, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import ActiveVote, Cluster, GalleryItem, VoteEvent, VoteTotal


class VoteRateLimiter(Protocol):
    def allow(self, key: str) -> bool: ...


class InMemorySlidingWindowLimiter:
    """Safe development hook; replace with an edge/shared backend for >1 worker."""

    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            queue = self._events[key]
            while queue and queue[0] <= now - self.window_seconds:
                queue.popleft()
            if len(queue) >= self.limit:
                return False
            queue.append(now)
            return True


def target_exists(session: Session, kind: str, target_id: str) -> bool:
    model = GalleryItem if kind == "item" else Cluster
    return session.get(model, target_id) is not None


def set_vote(
    session: Session,
    *,
    actor_id: str,
    kind: str,
    target_id: str,
    enabled: bool,
    network_hmac: str | None,
) -> tuple[bool, int]:
    active = session.scalar(
        select(ActiveVote).where(
            ActiveVote.actor_id == actor_id,
            ActiveVote.target_kind == kind,
            ActiveVote.target_id == target_id,
        )
    )
    changed = False
    if enabled and active is None:
        try:
            with session.begin_nested():
                session.add(ActiveVote(actor_id=actor_id, target_kind=kind, target_id=target_id))
                session.flush()
        except IntegrityError:  # a concurrent identical PUT won the uniqueness race
            active = session.scalar(
                select(ActiveVote).where(
                    ActiveVote.actor_id == actor_id,
                    ActiveVote.target_kind == kind,
                    ActiveVote.target_id == target_id,
                )
            )
        else:
            session.add(
                VoteEvent(
                    actor_id=actor_id,
                    target_kind=kind,
                    target_id=target_id,
                    operation="add",
                    network_hmac=network_hmac,
                )
            )
            changed = True
    elif not enabled:
        deletion = session.execute(
            delete(ActiveVote).where(
                ActiveVote.actor_id == actor_id,
                ActiveVote.target_kind == kind,
                ActiveVote.target_id == target_id,
            )
        )
        if deletion.rowcount:
            session.add(
                VoteEvent(
                    actor_id=actor_id,
                    target_kind=kind,
                    target_id=target_id,
                    operation="remove",
                    network_hmac=network_hmac,
                )
            )
            changed = True
    session.flush()
    count = (
        session.scalar(
            select(func.count(ActiveVote.id)).where(
                ActiveVote.target_kind == kind, ActiveVote.target_id == target_id
            )
        )
        or 0
    )
    if changed:
        _apply_total_delta(session, kind, target_id, 1 if enabled else -1)
    session.commit()
    current = (
        enabled
        if changed
        else (
            session.scalar(
                select(ActiveVote.id).where(
                    ActiveVote.actor_id == actor_id,
                    ActiveVote.target_kind == kind,
                    ActiveVote.target_id == target_id,
                )
            )
            is not None
        )
    )
    return current, count


def _apply_total_delta(session: Session, kind: str, target_id: str, delta: int) -> None:
    dialect = session.get_bind().dialect.name
    values = {"target_kind": kind, "target_id": target_id, "count": max(0, delta)}
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert

        statement = insert(VoteTotal).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[VoteTotal.target_kind, VoteTotal.target_id],
            set_={"count": func.greatest(0, VoteTotal.count + delta)},
        )
        session.execute(statement)
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert

        statement = insert(VoteTotal).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[VoteTotal.target_kind, VoteTotal.target_id],
            set_={"count": func.max(0, VoteTotal.count + delta)},
        )
        session.execute(statement)
    else:
        total = session.get(VoteTotal, (kind, target_id))
        if total is None:
            session.add(VoteTotal(**values))
        else:
            total.count = max(0, total.count + delta)


def audit_suspicious_actors(
    session: Session, *, hours: int = 24, minimum_events: int = 10, limit: int = 100
) -> list[dict[str, object]]:
    since = datetime.now(UTC) - timedelta(hours=hours)
    rows = session.execute(
        select(
            VoteEvent.actor_id,
            func.count(VoteEvent.id).label("event_count"),
            func.count(func.distinct(VoteEvent.target_id)).label("target_count"),
            func.count(func.distinct(VoteEvent.network_hmac)).label("network_count"),
            func.max(VoteEvent.created_at).label("last_event_at"),
        )
        .where(VoteEvent.created_at >= since)
        .group_by(VoteEvent.actor_id)
        .having(func.count(VoteEvent.id) >= minimum_events)
        .order_by(desc("event_count"))
        .limit(limit)
    ).all()
    return [
        {
            "actor_id": row.actor_id,
            "event_count": row.event_count,
            "target_count": row.target_count,
            "network_count": row.network_count,
            "last_event_at": row.last_event_at,
        }
        for row in rows
    ]


def rebuild_vote_totals(session: Session) -> int:
    session.execute(delete(VoteTotal))
    rows = session.execute(
        select(ActiveVote.target_kind, ActiveVote.target_id, func.count(ActiveVote.id)).group_by(
            ActiveVote.target_kind, ActiveVote.target_id
        )
    ).all()
    for kind, target_id, count in rows:
        session.add(VoteTotal(target_kind=kind, target_id=target_id, count=count))
    session.commit()
    return len(rows)
