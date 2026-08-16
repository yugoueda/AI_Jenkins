"""track the review event requested by each CI run

Revision ID: 0004_add_ci_review_event_type
Revises: 0003_add_ci_runs
Create Date: 2026-08-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_add_ci_review_event_type"
down_revision: Union[str, None] = "0003_add_ci_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_ci_runs() -> None:
    op.create_table(
        "ci_runs",
        sa.Column("project_id", sa.Text(), primary_key=True),
        sa.Column("mr_id", sa.Text(), primary_key=True),
        sa.Column("commit_sha", sa.Text(), primary_key=True),
        sa.Column("review_event_type", sa.Text(), primary_key=True),
        sa.Column("source_branch", sa.Text(), nullable=False),
        sa.Column("target_branch", sa.Text(), nullable=False),
        sa.Column("repository_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "review_event_type IN ('REVIEW', 'RE_REVIEW')",
            name="ck_ci_runs_review_event_type",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'TRIGGERING', 'RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_ci_runs_status",
        ),
    )
    op.create_index(
        "idx_ci_runs_project_mr_status",
        "ci_runs",
        ["project_id", "mr_id", "status"],
    )
    op.create_index("idx_ci_runs_created_at", "ci_runs", ["created_at"])


def upgrade() -> None:
    op.rename_table("ci_runs", "ci_runs_legacy")
    op.drop_index("idx_ci_runs_created_at", table_name="ci_runs_legacy")
    op.drop_index("idx_ci_runs_project_mr_status", table_name="ci_runs_legacy")
    _create_ci_runs()
    op.execute(
        "INSERT INTO ci_runs "
        "(project_id, mr_id, commit_sha, review_event_type, source_branch, "
        "target_branch, repository_url, status, created_at, started_at, completed_at) "
        "SELECT project_id, mr_id, commit_sha, 'REVIEW', source_branch, "
        "target_branch, repository_url, status, created_at, started_at, completed_at "
        "FROM ci_runs_legacy"
    )
    op.drop_table("ci_runs_legacy")


def downgrade() -> None:
    op.rename_table("ci_runs", "ci_runs_with_event")
    op.drop_index("idx_ci_runs_created_at", table_name="ci_runs_with_event")
    op.drop_index("idx_ci_runs_project_mr_status", table_name="ci_runs_with_event")
    op.create_table(
        "ci_runs",
        sa.Column("project_id", sa.Text(), primary_key=True),
        sa.Column("mr_id", sa.Text(), primary_key=True),
        sa.Column("commit_sha", sa.Text(), primary_key=True),
        sa.Column("source_branch", sa.Text(), nullable=False),
        sa.Column("target_branch", sa.Text(), nullable=False),
        sa.Column("repository_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'TRIGGERING', 'RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_ci_runs_status",
        ),
    )
    op.execute(
        "INSERT OR IGNORE INTO ci_runs "
        "(project_id, mr_id, commit_sha, source_branch, target_branch, "
        "repository_url, status, created_at, started_at, completed_at) "
        "SELECT project_id, mr_id, commit_sha, source_branch, target_branch, "
        "repository_url, status, created_at, started_at, completed_at "
        "FROM ci_runs_with_event ORDER BY created_at"
    )
    op.drop_table("ci_runs_with_event")
    op.create_index(
        "idx_ci_runs_project_mr_status",
        "ci_runs",
        ["project_id", "mr_id", "status"],
    )
    op.create_index("idx_ci_runs_created_at", "ci_runs", ["created_at"])
