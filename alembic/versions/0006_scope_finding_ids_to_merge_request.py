"""scope finding IDs to merge requests

Revision ID: 0006_scope_finding_ids_to_merge_request
Revises: 0005_add_review_checkpoints
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_scope_finding_ids_to_merge_request"
down_revision: Union[str, None] = "0005_add_review_checkpoints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_findings_table(name: str, composite_primary_key: bool) -> None:
    columns = [
        sa.Column("id", sa.Text(), nullable=False),
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
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("source IN ('AI')", name="ck_findings_source"),
        sa.CheckConstraint(
            "status IN ('OPEN', 'APPLIED', 'REJECTED')",
            name="ck_findings_status",
        ),
    ]
    if composite_primary_key:
        columns.append(sa.PrimaryKeyConstraint("mr_id", "id"))
    else:
        columns.append(sa.PrimaryKeyConstraint("id"))
    op.create_table(name, *columns)


def _copy_findings(source: str, destination: str) -> None:
    columns = (
        "id, mr_id, source, status, author, file_path, line_start, line_end, "
        "description, suggestion, fix_patch, fix_patch_sha256, created_at, updated_at"
    )
    op.execute(sa.text(f"INSERT INTO {destination} ({columns}) SELECT {columns} FROM {source}"))


def _replace_findings(composite_primary_key: bool) -> None:
    temporary_name = "findings_replacement"
    _create_findings_table(temporary_name, composite_primary_key)
    _copy_findings("findings", temporary_name)
    op.drop_table("findings")
    op.rename_table(temporary_name, "findings")
    op.create_index("idx_findings_mr_id", "findings", ["mr_id"])
    op.create_index("idx_findings_status", "findings", ["status"])
    op.create_index("idx_findings_mr_id_status", "findings", ["mr_id", "status"])


def upgrade() -> None:
    _replace_findings(composite_primary_key=True)


def downgrade() -> None:
    _replace_findings(composite_primary_key=False)
