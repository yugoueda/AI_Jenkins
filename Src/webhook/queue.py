import json
import uuid

from ..db.Src import database as db


def enqueue(mr_id: str, event_type: str, payload: dict) -> str:
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
