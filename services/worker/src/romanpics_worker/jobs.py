"""Backend-compatible SQLite and PostgreSQL lease queues."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from .contracts import JOB_TYPES, JobContractError, validate_job_payload


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Job:
    id: str
    job_type: str
    payload: dict[str, Any]
    status: str
    priority: int
    attempts: int
    max_attempts: int
    available_at: datetime
    locked_by: str | None
    locked_at: datetime | None
    dedupe_key: str | None


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _decoded_json(value: Any) -> Any:
    if value is None or isinstance(value, dict | list):
        return value
    if isinstance(value, bytes):
        value = value.decode()
    return json.loads(value)


def _aware(value: datetime | str | float | int | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, UTC)
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _stamp(value: datetime) -> str:
    aware = value if value.tzinfo else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f+00:00")


class JobStore:
    """SQLite implementation matching the backend Job columns and jobs-v1 payloads."""

    def __init__(
        self,
        database: str | Path | sqlite3.Connection,
        *,
        clock: Callable[[], datetime] = utcnow,
        initialize: bool = True,
    ):
        self.clock = clock
        if isinstance(database, sqlite3.Connection):
            self.connection = database
            self._owns_connection = False
        else:
            self.connection = sqlite3.connect(
                str(database), isolation_level=None, check_same_thread=False
            )
            self._owns_connection = True
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 5000")
        if initialize:
            self.initialize()

    def close(self) -> None:
        if self._owns_connection:
            self.connection.close()

    def __enter__(self) -> JobStore:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                job_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
                priority INTEGER NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                max_attempts INTEGER NOT NULL DEFAULT 5 CHECK (max_attempts > 0),
                available_at TEXT NOT NULL,
                locked_by TEXT,
                locked_at TEXT,
                dedupe_key TEXT UNIQUE,
                result_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_jobs_claim
                ON jobs (status, available_at, priority DESC, id ASC);
            """
        )

    @staticmethod
    def _from_row(row: Mapping[str, Any]) -> Job:
        available_at = _aware(row["available_at"])
        if available_at is None:
            raise RuntimeError("job has no available_at timestamp")
        payload = _decoded_json(row["payload_json"])
        if not isinstance(payload, dict):
            raise JobContractError("payload_json must be an object")
        return Job(
            id=str(row["id"]),
            job_type=str(row["job_type"]),
            payload=payload,
            status=str(row["status"]),
            priority=int(row["priority"]),
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
            available_at=available_at,
            locked_by=row["locked_by"],
            locked_at=_aware(row["locked_at"]),
            dedupe_key=row["dedupe_key"],
        )

    def enqueue(
        self,
        job_type: str,
        payload: Mapping[str, Any],
        *,
        priority: int = 0,
        max_attempts: int = 5,
        available_at: datetime | None = None,
        dedupe_key: str | None = None,
    ) -> str:
        validated = validate_job_payload(job_type, payload)
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        now = self.clock()
        available = now if available_at is None else available_at
        job_id = str(uuid.uuid4())
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO jobs (
                id, job_type, payload_json, priority, max_attempts, available_at,
                dedupe_key, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                job_type,
                _json(validated),
                priority,
                max_attempts,
                _stamp(available),
                dedupe_key,
                _stamp(now),
                _stamp(now),
            ),
        )
        if cursor.rowcount == 1:
            return job_id
        row = self.connection.execute(
            "SELECT id FROM jobs WHERE dedupe_key = ?", (dedupe_key,)
        ).fetchone()
        if row is None:
            raise RuntimeError("failed to enqueue or recover deduplicated job")
        return str(row["id"])

    def get(self, job_id: str) -> Job | None:
        row = self.connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._from_row(row) if row else None

    def result(self, job_id: str) -> Any:
        row = self.connection.execute(
            "SELECT result_json FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return _decoded_json(row["result_json"]) if row and row["result_json"] is not None else None

    def error(self, job_id: str) -> str | None:
        row = self.connection.execute("SELECT error FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return row["error"] if row else None

    def claim(self, worker_id: str) -> Job | None:
        if not worker_id:
            raise ValueError("worker_id is required")
        now = self.clock()
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row = self.connection.execute(
                """
                SELECT * FROM jobs
                WHERE status = 'queued' AND available_at <= ? AND attempts < max_attempts
                ORDER BY priority DESC, available_at ASC, id ASC
                LIMIT 1
                """,
                (_stamp(now),),
            ).fetchone()
            if row is None:
                self.connection.execute("COMMIT")
                return None
            self.connection.execute(
                """
                UPDATE jobs
                SET status = 'running', attempts = attempts + 1,
                    locked_by = ?, locked_at = ?, updated_at = ?, error = NULL
                WHERE id = ?
                """,
                (worker_id, _stamp(now), _stamp(now), row["id"]),
            )
            claimed = self.connection.execute(
                "SELECT * FROM jobs WHERE id = ?", (row["id"],)
            ).fetchone()
            self.connection.execute("COMMIT")
            return self._from_row(claimed)
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def heartbeat(self, job_id: str, worker_id: str) -> bool:
        now = self.clock()
        cursor = self.connection.execute(
            """
            UPDATE jobs SET locked_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND locked_by = ?
            """,
            (_stamp(now), _stamp(now), job_id, worker_id),
        )
        return cursor.rowcount == 1

    def complete(self, job_id: str, worker_id: str, result: Any = None) -> None:
        if result is not None and not isinstance(result, Mapping):
            raise ValueError("backend result_json must be an object or null")
        now = self.clock()
        cursor = self.connection.execute(
            """
            UPDATE jobs
            SET status = 'succeeded', result_json = ?, locked_by = NULL,
                locked_at = NULL, updated_at = ?
            WHERE id = ? AND status = 'running' AND locked_by = ?
            """,
            (_json(dict(result)) if result is not None else None, _stamp(now), job_id, worker_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("job is not owned by this worker")

    def fail(
        self,
        job_id: str,
        worker_id: str,
        error: str,
        *,
        retry_delay: float,
    ) -> str:
        now = self.clock()
        row = self.connection.execute(
            """SELECT attempts, max_attempts FROM jobs
               WHERE id = ? AND status = 'running' AND locked_by = ?""",
            (job_id, worker_id),
        ).fetchone()
        if row is None:
            raise RuntimeError("job is not owned by this worker")
        retry = row["attempts"] < row["max_attempts"]
        status = "queued" if retry else "failed"
        available = now + timedelta(seconds=max(0.0, retry_delay)) if retry else now
        self.connection.execute(
            """
            UPDATE jobs
            SET status = ?, available_at = ?, error = ?, locked_by = NULL,
                locked_at = NULL, updated_at = ?
            WHERE id = ?
            """,
            (status, _stamp(available), error[:4000], _stamp(now), job_id),
        )
        return status

    def requeue_stale(self, *, stale_after: float) -> int:
        if stale_after < 0:
            raise ValueError("stale_after must be non-negative")
        now = self.clock()
        stale_before = now - timedelta(seconds=stale_after)
        cursor = self.connection.execute(
            """
            UPDATE jobs
            SET status = CASE WHEN attempts < max_attempts THEN 'queued' ELSE 'failed' END,
                available_at = ?, error = 'worker lease expired',
                locked_by = NULL, locked_at = NULL, updated_at = ?
            WHERE status = 'running' AND locked_at < ?
            """,
            (_stamp(now), _stamp(now), _stamp(stale_before)),
        )
        return cursor.rowcount


class PostgresJobStore:
    """psycopg 3 lease queue for the backend's canonical ``jobs`` table."""

    def __init__(self, database: str | Any, *, initialize: bool = False):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError("psycopg 3 is required for PostgreSQL jobs") from error

        if isinstance(database, str):
            dsn = database.replace("postgresql+psycopg://", "postgresql://", 1)
            self.connection = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
            self._owns_connection = True
        else:
            self.connection = database
            self.connection.row_factory = dict_row
            self._owns_connection = False
        if initialize:
            self.initialize()

    def close(self) -> None:
        if self._owns_connection:
            self.connection.close()

    def __enter__(self) -> PostgresJobStore:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def initialize(self) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id varchar(36) PRIMARY KEY,
                    job_type varchar(100) NOT NULL,
                    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
                    status varchar(20) NOT NULL DEFAULT 'queued'
                        CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
                    priority integer NOT NULL DEFAULT 0,
                    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                    max_attempts integer NOT NULL DEFAULT 5 CHECK (max_attempts > 0),
                    available_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    locked_by varchar(255),
                    locked_at timestamptz,
                    dedupe_key varchar(512) UNIQUE,
                    result_json jsonb,
                    error text,
                    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """CREATE INDEX IF NOT EXISTS ix_jobs_claim
                   ON jobs (status, available_at, priority DESC, id ASC)"""
            )

    @staticmethod
    def _from_row(row: Mapping[str, Any]) -> Job:
        return JobStore._from_row(row)

    @staticmethod
    def _jsonb(value: Mapping[str, Any]) -> Any:
        from psycopg.types.json import Jsonb

        return Jsonb(dict(value))

    def enqueue(
        self,
        job_type: str,
        payload: Mapping[str, Any],
        *,
        priority: int = 0,
        max_attempts: int = 5,
        available_at: datetime | None = None,
        dedupe_key: str | None = None,
    ) -> str:
        validated = validate_job_payload(job_type, payload)
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        job_id = str(uuid.uuid4())
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO jobs (
                    id, job_type, payload_json, priority, max_attempts,
                    available_at, dedupe_key, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, COALESCE(%s, CURRENT_TIMESTAMP), %s,
                          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (dedupe_key) DO NOTHING
                RETURNING id
                """,
                (
                    job_id,
                    job_type,
                    self._jsonb(validated),
                    priority,
                    max_attempts,
                    available_at,
                    dedupe_key,
                ),
            )
            row = cursor.fetchone()
            if row:
                return str(row["id"])
            cursor.execute("SELECT id FROM jobs WHERE dedupe_key = %s", (dedupe_key,))
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("failed to enqueue or recover deduplicated job")
            return str(row["id"])

    def get(self, job_id: str) -> Job | None:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
            row = cursor.fetchone()
        return self._from_row(row) if row else None

    def result(self, job_id: str) -> Any:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT result_json FROM jobs WHERE id = %s", (job_id,))
            row = cursor.fetchone()
        return row["result_json"] if row else None

    def error(self, job_id: str) -> str | None:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT error FROM jobs WHERE id = %s", (job_id,))
            row = cursor.fetchone()
        return row["error"] if row else None

    def claim(self, worker_id: str) -> Job | None:
        if not worker_id:
            raise ValueError("worker_id is required")
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                WITH candidate AS (
                    SELECT id FROM jobs
                    WHERE status = 'queued'
                      AND available_at <= CURRENT_TIMESTAMP
                      AND attempts < max_attempts
                    ORDER BY priority DESC, available_at ASC, id ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE jobs AS job
                SET status = 'running', attempts = job.attempts + 1,
                    locked_by = %s, locked_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP, error = NULL
                FROM candidate
                WHERE job.id = candidate.id
                RETURNING job.*
                """,
                (worker_id,),
            )
            row = cursor.fetchone()
        return self._from_row(row) if row else None

    def heartbeat(self, job_id: str, worker_id: str) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE jobs SET locked_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND status = 'running' AND locked_by = %s
                """,
                (job_id, worker_id),
            )
            return cursor.rowcount == 1

    def complete(self, job_id: str, worker_id: str, result: Any = None) -> None:
        if result is not None and not isinstance(result, Mapping):
            raise ValueError("backend result_json must be an object or null")
        encoded = self._jsonb(result) if result is not None else None
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE jobs
                SET status = 'succeeded', result_json = %s, locked_by = NULL,
                    locked_at = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND status = 'running' AND locked_by = %s
                """,
                (encoded, job_id, worker_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("job is not owned by this worker")

    def fail(
        self,
        job_id: str,
        worker_id: str,
        error: str,
        *,
        retry_delay: float,
    ) -> str:
        delay = timedelta(seconds=max(0.0, retry_delay))
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE jobs
                SET status = CASE WHEN attempts < max_attempts THEN 'queued' ELSE 'failed' END,
                    available_at = CASE
                        WHEN attempts < max_attempts THEN CURRENT_TIMESTAMP + %s
                        ELSE CURRENT_TIMESTAMP
                    END,
                    error = %s, locked_by = NULL, locked_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND status = 'running' AND locked_by = %s
                RETURNING status
                """,
                (delay, error[:4000], job_id, worker_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("job is not owned by this worker")
            return str(row["status"])

    def requeue_stale(self, *, stale_after: float) -> int:
        if stale_after < 0:
            raise ValueError("stale_after must be non-negative")
        lease = timedelta(seconds=stale_after)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE jobs
                SET status = CASE WHEN attempts < max_attempts THEN 'queued' ELSE 'failed' END,
                    available_at = CURRENT_TIMESTAMP, error = 'worker lease expired',
                    locked_by = NULL, locked_at = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE status = 'running' AND locked_at < CURRENT_TIMESTAMP - %s
                """,
                (lease,),
            )
            return cursor.rowcount


Handler = Callable[[Job], Mapping[str, Any]]


class JobStoreProtocol(Protocol):
    def claim(self, worker_id: str) -> Job | None: ...

    def heartbeat(self, job_id: str, worker_id: str) -> bool: ...

    def complete(
        self, job_id: str, worker_id: str, result: Mapping[str, Any] | None = None
    ) -> None: ...

    def fail(self, job_id: str, worker_id: str, error: str, *, retry_delay: float) -> str: ...

    def requeue_stale(self, *, stale_after: float) -> int: ...


def sqlite_path_from_url(database_url: str) -> str:
    if not database_url.startswith("sqlite:///"):
        raise ValueError("SQLite URL must start with sqlite:///")
    return database_url.removeprefix("sqlite:///")


def open_job_store(
    *,
    database: str | Path | None = None,
    database_url: str | None = None,
    initialize: bool = False,
) -> JobStore | PostgresJobStore:
    if database_url and database is not None:
        raise ValueError("choose either a SQLite database path or --database-url")
    if database_url:
        if database_url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
            return PostgresJobStore(database_url, initialize=initialize)
        if database_url.startswith("sqlite:///"):
            return JobStore(sqlite_path_from_url(database_url), initialize=initialize)
        raise ValueError("database URL must use PostgreSQL/psycopg or SQLite")
    if database is None:
        raise ValueError("a SQLite database path or --database-url is required")
    return JobStore(database, initialize=initialize)


class Worker:
    def __init__(
        self,
        store: JobStoreProtocol,
        handlers: Mapping[str, Handler],
        *,
        worker_id: str,
        base_retry_delay: float = 5.0,
        max_retry_delay: float = 300.0,
        heartbeat_interval: float = 30.0,
    ):
        if set(handlers) != set(JOB_TYPES):
            raise ValueError(f"handlers must be exactly: {', '.join(JOB_TYPES)}")
        self.store = store
        self.handlers = dict(handlers)
        self.worker_id = worker_id
        self.base_retry_delay = base_retry_delay
        self.max_retry_delay = max_retry_delay
        self.heartbeat_interval = heartbeat_interval

    def run_once(self) -> bool:
        job = self.store.claim(self.worker_id)
        if job is None:
            return False
        stop_heartbeat = threading.Event()
        heartbeat_thread: threading.Thread | None = None
        if self.heartbeat_interval > 0:

            def heartbeat() -> None:
                while not stop_heartbeat.wait(self.heartbeat_interval):
                    if not self.store.heartbeat(job.id, self.worker_id):
                        return

            heartbeat_thread = threading.Thread(
                target=heartbeat,
                name=f"job-heartbeat-{job.id}",
                daemon=True,
            )
            heartbeat_thread.start()
        result: Mapping[str, Any] | None = None
        failure: Exception | None = None
        try:
            validated = validate_job_payload(job.job_type, job.payload)
            job = replace(job, payload=dict(validated))
            result = self.handlers[job.job_type](job)
        except Exception as error:  # A single bad product must not terminate the worker.
            failure = error
        finally:
            stop_heartbeat.set()
            if heartbeat_thread is not None:
                heartbeat_thread.join(timeout=max(1.0, self.heartbeat_interval + 1.0))
        if failure is not None:
            retry_delay = min(
                self.max_retry_delay, self.base_retry_delay * (2 ** max(0, job.attempts - 1))
            )
            self.store.fail(
                job.id,
                self.worker_id,
                f"{type(failure).__name__}: {failure}",
                retry_delay=retry_delay,
            )
        else:
            self.store.complete(job.id, self.worker_id, result)
        return True

    def run_forever(
        self,
        *,
        stop_event: threading.Event | None = None,
        poll_interval: float = 1.0,
        max_jobs: int | None = None,
    ) -> int:
        stop = stop_event or threading.Event()
        processed = 0
        while not stop.is_set() and (max_jobs is None or processed < max_jobs):
            if self.run_once():
                processed += 1
            else:
                stop.wait(max(0.0, poll_interval))
        return processed
