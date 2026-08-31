from __future__ import annotations

import inspect
import json
import sqlite3
from pathlib import Path

import pytest

from romanpics_worker.contracts import JOB_TYPES, JobContractError, validate_job_payload
from romanpics_worker.handlers import build_handlers
from romanpics_worker.jobs import JobStore, PostgresJobStore, Worker, open_job_store

ITEM_ID = "11111111-1111-4111-8111-111111111111"
PRODUCT_ID = "22222222-2222-4222-8222-222222222222"
RECORD_ID = "33333333-3333-4333-8333-333333333333"
SOURCE_ID = "44444444-4444-4444-8444-444444444444"
RUN_ID = "55555555-5555-4555-8555-555555555555"


VALID = {
    "render": {"item_id": ITEM_ID, "product_id": PRODUCT_ID, "recipe": {"version": "v1"}},
    "embed": {"item_id": ITEM_ID, "source_record_id": RECORD_ID, "checksum": "a" * 64},
    "cluster": {"source_id": SOURCE_ID, "ingest_run_id": RUN_ID},
    "link-check": {"scope": "catalog"},
}


def test_runtime_contract_matches_checked_in_backend_schema_titles() -> None:
    contract = json.loads((Path(__file__).parents[1] / "docs" / "job-contract.json").read_text())
    assert contract["$id"] == "https://romanpics.org/contracts/jobs-v1.json"
    assert tuple(branch["title"] for branch in contract["oneOf"]) == JOB_TYPES
    for job_type in JOB_TYPES:
        assert validate_job_payload(job_type, VALID[job_type]) == VALID[job_type]


@pytest.mark.parametrize(
    ("job_type", "payload", "message"),
    [
        ("custom", {}, "unsupported"),
        ("render", {**VALID["render"], "url": "https://evil.invalid"}, "unexpected"),
        ("render", {**VALID["render"], "item_id": "not-a-uuid"}, "UUID"),
        ("embed", {**VALID["embed"], "checksum": "ABC"}, "checksum"),
        ("cluster", {"source_id": SOURCE_ID}, "missing"),
        ("link-check", {"scope": "", "url": "https://evil.invalid"}, "unexpected"),
    ],
)
def test_contract_rejects_unknown_types_fields_and_bad_formats(
    job_type: str, payload: dict[str, object], message: str
) -> None:
    with pytest.raises(JobContractError, match=message):
        validate_job_payload(job_type, payload)


def test_enqueue_validates_and_worker_dead_letters_an_invalid_existing_row() -> None:
    connection = sqlite3.connect(":memory:", isolation_level=None)
    store = JobStore(connection)
    with pytest.raises(JobContractError):
        store.enqueue("render", {"source_path": "/tmp/input.fits"})

    job_id = store.enqueue("link-check", VALID["link-check"], max_attempts=1)
    connection.execute(
        "UPDATE jobs SET payload_json = ? WHERE id = ?",
        (json.dumps({"scope": "catalog", "url": "https://evil.invalid"}), job_id),
    )
    worker = Worker(
        store,
        build_handlers(),
        worker_id="validator",
        heartbeat_interval=0,
    )
    assert worker.run_once()
    assert store.get(job_id).status == "failed"
    assert "JobContractError" in store.error(job_id)


def test_database_url_selects_sqlite_and_postgres_claim_uses_skip_locked(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    store = open_job_store(database_url=f"sqlite:///{database}", initialize=True)
    try:
        assert isinstance(store, JobStore)
    finally:
        store.close()
    claim_source = inspect.getsource(PostgresJobStore.claim)
    assert "FOR UPDATE SKIP LOCKED" in claim_source
    assert "RETURNING job.*" in claim_source
