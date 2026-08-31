from sqlalchemy import func, select

from romanpics_api.models import Job
from romanpics_api.services.jobs import enqueue_job, enqueue_link_check, retry_failed_jobs


def test_daily_link_check_enqueue_is_idempotent(database):
    _, factory = database

    with factory() as session:
        first, first_created = enqueue_link_check(session)
        session.commit()
        first_id = first.id

    with factory() as session:
        second, second_created = enqueue_link_check(session)
        session.commit()

        assert first_created is True
        assert second_created is False
        assert second.id == first_id
        assert second.status == "queued"
        assert second.payload_json == {"scope": "catalog"}
        assert session.scalar(select(func.count(Job.id))) == 1


def test_failed_deduplicated_job_can_be_requeued(database):
    _, factory = database
    with factory() as session:
        job, _ = enqueue_job(
            session,
            job_type="embed",
            payload_json={"item_id": "item", "source_record_id": "record", "checksum": "abc"},
            dedupe_key="embed:item:abc",
        )
        job.status = "failed"
        job.attempts = job.max_attempts
        job.error = "temporary model failure"
        session.commit()
        identifier = job.id

    with factory() as session:
        assert retry_failed_jobs(session, job_type="embed", limit=1) == [identifier]
        session.commit()
        retried = session.get(Job, identifier)
        assert retried.status == "queued"
        assert retried.attempts == 0
        assert retried.error is None
        assert retried.dedupe_key == "embed:item:abc"
