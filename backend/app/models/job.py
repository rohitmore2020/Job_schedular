import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from sqlalchemy import (
    String, Integer, Boolean, DateTime, Text, ForeignKey,
    Index, Enum as SQLEnum, text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from backend.app.core.database import Base
from backend.app.models.enums import JobStatus, ExecutionStatus

if TYPE_CHECKING:
    from backend.app.models.queue import Queue


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    queue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(JobStatus, values_callable=lambda x: [e.value for e in x], native_enum=True),
        default=JobStatus.QUEUED,
        nullable=False,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    # Timestamps & Scheduling
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now, nullable=False, index=True
    )
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Concurrency Lock & Lease Fencing
    locked_by_worker_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    lease_token: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    lock_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # DAG & Dependencies
    parent_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tags: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False
    )

    __table_args__ = (
        Index(
            "idx_jobs_claim_ready",
            "queue_id",
            text("priority DESC"),
            text("run_at ASC"),
            postgresql_where=text("status = 'queued'"),
        ),
        Index(
            "idx_jobs_running_lease",
            "lock_expires_at",
            postgresql_where=text("status = 'running'"),
        ),
        Index(
            "idx_jobs_idempotency",
            "queue_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    # Relationships
    queue: Mapped["Queue"] = relationship("Queue", back_populates="jobs")
    batch: Mapped[Optional["JobBatch"]] = relationship("JobBatch", back_populates="jobs")
    executions: Mapped[List["JobExecution"]] = relationship(
        "JobExecution", back_populates="job", cascade="all, delete-orphan", order_by="JobExecution.attempt_number"
    )
    dlq_entry: Mapped[Optional["DLQEntry"]] = relationship(
        "DLQEntry", back_populates="job", uselist=False, cascade="all, delete-orphan"
    )
    parent_job: Mapped[Optional["Job"]] = relationship(
        "Job", remote_side=[id], backref="child_jobs"
    )


class JobExecution(Base):
    __tablename__ = "job_executions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    worker_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ExecutionStatus] = mapped_column(
        SQLEnum(ExecutionStatus, values_callable=lambda x: [e.value for e in x], native_enum=True),
        default=ExecutionStatus.SUCCESS,
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stack_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    job: Mapped["Job"] = relationship("Job", back_populates="executions")


class DLQEntry(Base):
    __tablename__ = "dead_letter_queue"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    queue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    failed_reason: Mapped[str] = mapped_column(Text, nullable=False)
    total_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_failure_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    moved_to_dlq_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now, nullable=False
    )
    is_replayed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    replayed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    job: Mapped["Job"] = relationship("Job", back_populates="dlq_entry")
    queue: Mapped["Queue"] = relationship("Queue", back_populates="dlq_entries")
