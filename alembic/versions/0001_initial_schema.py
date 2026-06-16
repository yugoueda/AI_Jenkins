"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "findings",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("mr_id", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("line_start", sa.Integer(), nullable=True),
        sa.Column("line_end", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("suggestion", sa.Text(), nullable=True),
        sa.Column("fix_patch", sa.Text(), nullable=True),
        sa.Column("fix_patch_sha256", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("source IN ('AI')", name="ck_findings_source"),
        sa.CheckConstraint(
            "status IN ('OPEN', 'APPLIED', 'REJECTED')",
            name="ck_findings_status",
        ),
    )
    op.create_index("idx_findings_mr_id", "findings", ["mr_id"])
    op.create_index("idx_findings_status", "findings", ["status"])
    op.create_index("idx_findings_mr_id_status", "findings", ["mr_id", "status"])

    op.create_table(
        "job_queue",
        sa.Column("job_id", sa.Text(), primary_key=True),
        sa.Column("mr_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="WAITING"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "event_type IN ('REVIEW', 'APPROVE', 'RE_REVIEW', 'UNIT_TEST_GEN')",
            name="ck_job_queue_event_type",
        ),
        sa.CheckConstraint(
            "status IN ('WAITING', 'PROCESSING', 'DONE', 'FAILED')",
            name="ck_job_queue_status",
        ),
    )
    op.create_index("idx_job_queue_status", "job_queue", ["status"])
    op.create_index("idx_job_queue_mr_id_status", "job_queue", ["mr_id", "status"])
    op.create_index("idx_job_queue_created_at", "job_queue", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_job_queue_created_at", table_name="job_queue")
    op.drop_index("idx_job_queue_mr_id_status", table_name="job_queue")
    op.drop_index("idx_job_queue_status", table_name="job_queue")
    op.drop_table("job_queue")

    op.drop_index("idx_findings_mr_id_status", table_name="findings")
    op.drop_index("idx_findings_status", table_name="findings")
    op.drop_index("idx_findings_mr_id", table_name="findings")
    op.drop_table("findings")
