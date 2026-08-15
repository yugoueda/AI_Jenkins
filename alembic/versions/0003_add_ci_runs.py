"""add CI run tracking

Revision ID: 0003_add_ci_runs
Revises: 0002_add_missing_job_types
Create Date: 2026-08-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_add_ci_runs"
down_revision: Union[str, None] = "0002_add_missing_job_types"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ci_runs",
        sa.Column("project_id", sa.Text(), primary_key=True),
        sa.Column("mr_id", sa.Text(), primary_key=True),
        sa.Column("commit_sha", sa.Text(), primary_key=True),
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


def downgrade() -> None:
    op.drop_index("idx_ci_runs_created_at", table_name="ci_runs")
    op.drop_index("idx_ci_runs_project_mr_status", table_name="ci_runs")
    op.drop_table("ci_runs")
