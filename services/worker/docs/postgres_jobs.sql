-- PostgreSQL reference for the backend-compatible psycopg JobStore.
-- In production Alembic owns this table; init-db is only for isolated workers/tests.

CREATE TABLE IF NOT EXISTS jobs (
    id varchar(36) PRIMARY KEY,
    job_type varchar(100) NOT NULL,
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    status varchar(20) NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
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
);

CREATE INDEX IF NOT EXISTS ix_jobs_claim
    ON jobs (status, available_at, priority DESC, id ASC);

-- Atomic claim. The UPDATE and row lock live in one statement/transaction, while
-- SKIP LOCKED lets concurrent workers choose different rows without Redis.
WITH candidate AS (
    SELECT id
    FROM jobs
    WHERE status = 'queued'
      AND available_at <= CURRENT_TIMESTAMP
      AND attempts < max_attempts
    ORDER BY priority DESC, available_at ASC, id ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE jobs AS job
SET status = 'running',
    attempts = job.attempts + 1,
    locked_by = :worker_id,
    locked_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP,
    error = NULL
FROM candidate
WHERE job.id = candidate.id
RETURNING job.*;

-- Heartbeat; require exactly one updated row or treat the lease as lost.
UPDATE jobs
SET locked_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
WHERE id = :job_id AND status = 'running' AND locked_by = :worker_id;

-- Failure/retry. attempts increments at claim. A final failure remains in the
-- canonical table as status='failed', which is the backend's dead-letter state.
UPDATE jobs
SET status = CASE WHEN attempts < max_attempts THEN 'queued' ELSE 'failed' END,
    available_at = CASE
        WHEN attempts < max_attempts
            THEN CURRENT_TIMESTAMP + (:retry_seconds * interval '1 second')
        ELSE CURRENT_TIMESTAMP
    END,
    error = left(:error, 4000),
    locked_by = NULL,
    locked_at = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :job_id AND status = 'running' AND locked_by = :worker_id
RETURNING status;

-- Lease recovery follows the same retry/dead-letter rule.
UPDATE jobs
SET status = CASE WHEN attempts < max_attempts THEN 'queued' ELSE 'failed' END,
    available_at = CURRENT_TIMESTAMP,
    error = 'worker lease expired',
    locked_by = NULL,
    locked_at = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE status = 'running'
  AND locked_at < CURRENT_TIMESTAMP - (:lease_seconds * interval '1 second');
