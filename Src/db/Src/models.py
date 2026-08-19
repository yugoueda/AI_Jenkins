from sqlalchemy import CheckConstraint, DateTime, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Finding(Base):
    __tablename__ = "findings"

    # 指摘ID（R1, R2, ...）はMRごとに採番する。
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    mr_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text)
    line_start: Mapped[int | None] = mapped_column(Integer)
    line_end: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    suggestion: Mapped[str | None] = mapped_column(Text)
    fix_patch: Mapped[str | None] = mapped_column(Text)
    fix_patch_sha256: Mapped[str | None] = mapped_column(Text)
    created_at = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())

    __table_args__ = (
        CheckConstraint("source IN ('AI')", name="ck_findings_source"),
        CheckConstraint(
            "status IN ('OPEN', 'APPLIED', 'REJECTED')",
            name="ck_findings_status",
        ),
        Index("idx_findings_mr_id", "mr_id"),
        Index("idx_findings_status", "status"),
        Index("idx_findings_mr_id_status", "mr_id", "status"),
    )


class JobQueue(Base):
    __tablename__ = "job_queue"

    job_id: Mapped[str] = mapped_column(Text, primary_key=True)
    mr_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="WAITING")
    created_at = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    started_at = mapped_column(DateTime)
    completed_at = mapped_column(DateTime)

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('BUILD_FIX', 'REVIEW', 'APPLY', 'APPROVE', "
            "'RE_REVIEW', 'UNIT_TEST_GEN')",
            name="ck_job_queue_event_type",
        ),
        CheckConstraint(
            "status IN ('WAITING', 'PROCESSING', 'DONE', 'FAILED')",
            name="ck_job_queue_status",
        ),
        Index("idx_job_queue_status", "status"),
        Index("idx_job_queue_mr_id_status", "mr_id", "status"),
        Index("idx_job_queue_created_at", "created_at"),
    )


class CiRun(Base):
    __tablename__ = "ci_runs"

    project_id: Mapped[str] = mapped_column(Text, primary_key=True)
    mr_id: Mapped[str] = mapped_column(Text, primary_key=True)
    commit_sha: Mapped[str] = mapped_column(Text, primary_key=True)
    review_event_type: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        default="REVIEW",
    )
    source_branch: Mapped[str] = mapped_column(Text, nullable=False)
    target_branch: Mapped[str] = mapped_column(Text, nullable=False)
    repository_url: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    started_at = mapped_column(DateTime)
    completed_at = mapped_column(DateTime)

    __table_args__ = (
        CheckConstraint(
            "review_event_type IN ('REVIEW', 'RE_REVIEW', 'POST_RESOLUTION')",
            name="ck_ci_runs_review_event_type",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'TRIGGERING', 'RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_ci_runs_status",
        ),
        Index(
            "idx_ci_runs_project_mr_status",
            "project_id",
            "mr_id",
            "status",
        ),
        Index("idx_ci_runs_created_at", "created_at"),
    )


class ReviewCheckpoint(Base):
    __tablename__ = "review_checkpoints"

    project_id: Mapped[str] = mapped_column(Text, primary_key=True)
    mr_id: Mapped[str] = mapped_column(Text, primary_key=True)
    commit_sha: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )
