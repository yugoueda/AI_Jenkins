"""add BUILD_FIX and APPLY job types

Revision ID: 0002_add_missing_job_types
Revises: 0001_initial_schema
Create Date: 2026-08-15

"""
from typing import Sequence, Union

from alembic import op


revision: str = "0002_add_missing_job_types"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("job_queue") as batch_op:
        batch_op.drop_constraint("ck_job_queue_event_type", type_="check")
        batch_op.create_check_constraint(
            "ck_job_queue_event_type",
            "event_type IN ('BUILD_FIX', 'REVIEW', 'APPLY', 'APPROVE', "
            "'RE_REVIEW', 'UNIT_TEST_GEN')",
        )


def downgrade() -> None:
    with op.batch_alter_table("job_queue") as batch_op:
        batch_op.drop_constraint("ck_job_queue_event_type", type_="check")
        batch_op.create_check_constraint(
            "ck_job_queue_event_type",
            "event_type IN ('REVIEW', 'APPROVE', 'RE_REVIEW', 'UNIT_TEST_GEN')",
        )
