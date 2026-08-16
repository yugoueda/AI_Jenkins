from ..db.Src import database as db


def get_review_checkpoint(project_id: str, mr_id: str) -> str | None:
    return db.query_scalar(
        "SELECT commit_sha FROM review_checkpoints "
        "WHERE project_id=:project_id AND mr_id=:mr_id",
        {"project_id": project_id, "mr_id": mr_id},
    )


def save_review_checkpoint(project_id: str, mr_id: str, commit_sha: str) -> None:
    db.execute(
        "INSERT INTO review_checkpoints "
        "(project_id, mr_id, commit_sha, updated_at) "
        "VALUES (:project_id, :mr_id, :commit_sha, CURRENT_TIMESTAMP) "
        "ON CONFLICT(project_id, mr_id) DO UPDATE SET "
        "commit_sha=excluded.commit_sha, updated_at=CURRENT_TIMESTAMP",
        {
            "project_id": project_id,
            "mr_id": mr_id,
            "commit_sha": commit_sha,
        },
    )
