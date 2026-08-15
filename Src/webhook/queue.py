import json
import uuid

from sqlalchemy import text

from ..db.Src import database as db


SUPPORTED_EVENT_TYPES = {
    "BUILD_FIX",
    "REVIEW",
    "APPLY",
    "APPROVE",
    "RE_REVIEW",
    "UNIT_TEST_GEN",
}


def enqueue(mr_id: str, event_type: str, payload: dict) -> str:
    if event_type not in SUPPORTED_EVENT_TYPES:
        raise ValueError(f"unsupported event_type: {event_type}")
    job_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO job_queue (job_id, mr_id, event_type, payload, status, created_at) "
        "VALUES (:job_id, :mr_id, :event_type, :payload, 'WAITING', CURRENT_TIMESTAMP)",
        {
            "job_id": job_id,
            "mr_id": mr_id,
            "event_type": event_type,
            "payload": json.dumps(payload, ensure_ascii=False),
        },
    )
    return job_id


def is_agent_busy() -> bool:
    return bool(
        db.query_scalar(
            "SELECT EXISTS(SELECT 1 FROM job_queue WHERE status='PROCESSING')"
        )
    )


def can_process(mr_id: str) -> bool:
    return not bool(
        db.query_scalar(
            "SELECT EXISTS("
            "SELECT 1 FROM job_queue "
            "WHERE mr_id=:mr_id AND status='PROCESSING'"
            ")",
            {"mr_id": mr_id},
        )
    )


def claim_next_waiting_job() -> dict | None:
    with db.engine.begin() as conn:
        if conn.execute(
            text("SELECT EXISTS(SELECT 1 FROM job_queue WHERE status='PROCESSING')")
        ).scalar():
            return None

        row = (
            conn.execute(
                text(
                    "SELECT job_id, mr_id, event_type, payload "
                    "FROM job_queue WHERE status='WAITING' "
                    "ORDER BY created_at, rowid LIMIT 1"
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None

        updated = conn.execute(
            text(
                "UPDATE job_queue "
                "SET status='PROCESSING', started_at=CURRENT_TIMESTAMP "
                "WHERE job_id=:job_id AND status='WAITING'"
            ),
            {"job_id": row["job_id"]},
        )
        return dict(row) if updated.rowcount == 1 else None


def complete_job(job_id: str, succeeded: bool) -> None:
    db.execute(
        "UPDATE job_queue "
        "SET status=:status, completed_at=CURRENT_TIMESTAMP "
        "WHERE job_id=:job_id AND status='PROCESSING'",
        {"job_id": job_id, "status": "DONE" if succeeded else "FAILED"},
    )


def recover_stale_jobs() -> int:
    with db.engine.begin() as conn:
        result = conn.execute(
            text(
                "UPDATE job_queue "
                "SET status='FAILED', completed_at=CURRENT_TIMESTAMP "
                "WHERE status='PROCESSING'"
            )
        )
        return result.rowcount
