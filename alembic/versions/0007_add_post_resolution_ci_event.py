"""add post-resolution CI event

Revision ID: 0007_add_post_resolution_ci_event
Revises: 0006_scope_finding_ids_to_merge_request
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op


revision: str = "0007_add_post_resolution_ci_event"
down_revision: Union[str, None] = "0006_scope_finding_ids_to_merge_request"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ci_runs") as batch_op:
        batch_op.drop_constraint("ck_ci_runs_review_event_type", type_="check")
        batch_op.create_check_constraint(
            "ck_ci_runs_review_event_type",
            "review_event_type IN ('REVIEW', 'RE_REVIEW', 'POST_RESOLUTION')",
        )


def downgrade() -> None:
    with op.batch_alter_table("ci_runs") as batch_op:
        batch_op.drop_constraint("ck_ci_runs_review_event_type", type_="check")
        batch_op.create_check_constraint(
            "ck_ci_runs_review_event_type",
            "review_event_type IN ('REVIEW', 'RE_REVIEW')",
        )
