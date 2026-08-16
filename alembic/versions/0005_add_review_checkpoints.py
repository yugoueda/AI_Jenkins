"""add successful review checkpoints

Revision ID: 0005_add_review_checkpoints
Revises: 0004_add_ci_review_event_type
Create Date: 2026-08-16

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_add_review_checkpoints"
down_revision: Union[str, None] = "0004_add_ci_review_event_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "review_checkpoints",
        sa.Column("project_id", sa.Text(), primary_key=True),
        sa.Column("mr_id", sa.Text(), primary_key=True),
        sa.Column("commit_sha", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # Use the latest completed review when upgrading an existing database.
    # Failed reviews deliberately do not advance the checkpoint.
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT mr_id, payload, completed_at FROM job_queue "
            "WHERE event_type IN ('REVIEW', 'RE_REVIEW') AND status='DONE' "
            "ORDER BY completed_at"
        )
    ).mappings()
    checkpoints: dict[tuple[str, str], tuple[str, object]] = {}
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except (TypeError, json.JSONDecodeError):
            continue
        project_id = str(payload.get("project_id") or "")
        commit_sha = str(payload.get("commit_sha") or "")
        if project_id and commit_sha:
            checkpoints[(project_id, str(row["mr_id"]))] = (
                commit_sha,
                row["completed_at"],
            )

    for (project_id, mr_id), (commit_sha, completed_at) in checkpoints.items():
        connection.execute(
            sa.text(
                "INSERT INTO review_checkpoints "
                "(project_id, mr_id, commit_sha, updated_at) "
                "VALUES (:project_id, :mr_id, :commit_sha, "
                "COALESCE(:completed_at, CURRENT_TIMESTAMP))"
            ),
            {
                "project_id": project_id,
                "mr_id": mr_id,
                "commit_sha": commit_sha,
                "completed_at": completed_at,
            },
        )


def downgrade() -> None:
    op.drop_table("review_checkpoints")
