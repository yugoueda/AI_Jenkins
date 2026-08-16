from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from ..db.Src import database as db


def reserve_ci_run(
    *,
    project_id: str,
    mr_id: str,
    commit_sha: str,
    source_branch: str,
    target_branch: str,
    repository_url: str,
    review_event_type: str = "REVIEW",
) -> str:
    """Reserve a commit once, queueing it when the same MR already has a build."""
    try:
        with db.engine.begin() as conn:
            status = conn.execute(
                text(
                    "SELECT CASE WHEN EXISTS("
                    "SELECT 1 FROM ci_runs "
                    "WHERE project_id=:project_id AND mr_id=:mr_id "
                    "AND status IN ('TRIGGERING', 'RUNNING')"
                    ") THEN 'PENDING' ELSE 'TRIGGERING' END"
                ),
                {"project_id": project_id, "mr_id": mr_id},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO ci_runs "
                    "(project_id, mr_id, commit_sha, review_event_type, source_branch, "
                    "target_branch, repository_url, status, created_at) "
                    "VALUES (:project_id, :mr_id, :commit_sha, :review_event_type, "
                    ":source_branch, :target_branch, :repository_url, :status, "
                    "CURRENT_TIMESTAMP)"
                ),
                {
                    "project_id": project_id,
                    "mr_id": mr_id,
                    "commit_sha": commit_sha,
                    "source_branch": source_branch,
                    "target_branch": target_branch,
                    "repository_url": repository_url,
                    "review_event_type": review_event_type,
                    "status": status,
                },
            )
            return str(status)
    except IntegrityError:
        return "DUPLICATE"


def mark_ci_run_running(
    project_id: str,
    mr_id: str,
    commit_sha: str,
    review_event_type: str = "REVIEW",
) -> None:
    db.execute(
        "UPDATE ci_runs SET status='RUNNING', started_at=CURRENT_TIMESTAMP "
        "WHERE project_id=:project_id AND mr_id=:mr_id AND commit_sha=:commit_sha "
        "AND review_event_type=:review_event_type AND status='TRIGGERING'",
        {
            "project_id": project_id,
            "mr_id": mr_id,
            "commit_sha": commit_sha,
            "review_event_type": review_event_type,
        },
    )


def mark_ci_run_completed(project_id: str, mr_id: str, commit_sha: str) -> str:
    if not commit_sha:
        return "REVIEW"
    row = db.query_one(
        "SELECT review_event_type FROM ci_runs "
        "WHERE project_id=:project_id AND mr_id=:mr_id AND commit_sha=:commit_sha "
        "AND status IN ('TRIGGERING', 'RUNNING') ORDER BY created_at DESC LIMIT 1",
        {"project_id": project_id, "mr_id": mr_id, "commit_sha": commit_sha},
    )
    review_event_type = str(row["review_event_type"]) if row else "REVIEW"
    db.execute(
        "UPDATE ci_runs SET status='COMPLETED', completed_at=CURRENT_TIMESTAMP "
        "WHERE project_id=:project_id AND mr_id=:mr_id AND commit_sha=:commit_sha "
        "AND review_event_type=:review_event_type "
        "AND status IN ('TRIGGERING', 'RUNNING')",
        {
            "project_id": project_id,
            "mr_id": mr_id,
            "commit_sha": commit_sha,
            "review_event_type": review_event_type,
        },
    )
    return review_event_type


def mark_ci_run_failed(
    project_id: str,
    mr_id: str,
    commit_sha: str,
    review_event_type: str = "REVIEW",
) -> None:
    db.execute(
        "UPDATE ci_runs SET status='FAILED', completed_at=CURRENT_TIMESTAMP "
        "WHERE project_id=:project_id AND mr_id=:mr_id AND commit_sha=:commit_sha "
        "AND review_event_type=:review_event_type AND status='TRIGGERING'",
        {
            "project_id": project_id,
            "mr_id": mr_id,
            "commit_sha": commit_sha,
            "review_event_type": review_event_type,
        },
    )


def claim_next_pending_ci_run(project_id: str, mr_id: str) -> dict | None:
    with db.engine.begin() as conn:
        active = conn.execute(
            text(
                "SELECT EXISTS(SELECT 1 FROM ci_runs "
                "WHERE project_id=:project_id AND mr_id=:mr_id "
                "AND status IN ('TRIGGERING', 'RUNNING'))"
            ),
            {"project_id": project_id, "mr_id": mr_id},
        ).scalar()
        if active:
            return None

        row = (
            conn.execute(
                text(
                    "SELECT project_id, mr_id, commit_sha, source_branch, "
                    "target_branch, repository_url, review_event_type FROM ci_runs "
                    "WHERE project_id=:project_id AND mr_id=:mr_id "
                    "AND status='PENDING' ORDER BY created_at, rowid LIMIT 1"
                ),
                {"project_id": project_id, "mr_id": mr_id},
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        updated = conn.execute(
            text(
                "UPDATE ci_runs SET status='TRIGGERING' "
                "WHERE project_id=:project_id AND mr_id=:mr_id "
                "AND commit_sha=:commit_sha AND review_event_type=:review_event_type "
                "AND status='PENDING'"
            ),
            dict(row),
        )
        return dict(row) if updated.rowcount == 1 else None
