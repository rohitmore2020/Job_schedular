import uuid
from datetime import datetime, timezone
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, Boolean, Float, DateTime, ForeignKey, UniqueConstraint, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from backend.app.core.database import Base
from backend.app.models.enums import RetryStrategy

if TYPE_CHECKING:
    from backend.app.models.project import Project
    from backend.app.models.job import Job, DLQEntry
    from backend.app.models.schedule import ScheduledJob


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Queue(Base):
    __tablename__ = "queues"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    concurrency_limit: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    rate_limit_rps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_queue_project_name"),
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="queues")
    retry_policy: Mapped[Optional["RetryPolicy"]] = relationship(
        "RetryPolicy", back_populates="queue", uselist=False, cascade="all, delete-orphan"
    )
    jobs: Mapped[List["Job"]] = relationship(
        "Job", back_populates="queue", cascade="all, delete-orphan"
    )
    dlq_entries: Mapped[List["DLQEntry"]] = relationship(
        "DLQEntry", back_populates="queue", cascade="all, delete-orphan"
    )
    scheduled_jobs: Mapped[List["ScheduledJob"]] = relationship(
        "ScheduledJob", back_populates="queue", cascade="all, delete-orphan"
    )


class RetryPolicy(Base):
    __tablename__ = "retry_policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    queue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queues.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    strategy: Mapped[RetryStrategy] = mapped_column(
        SQLEnum(RetryStrategy, values_callable=lambda x: [e.value for e in x], native_enum=True),
        default=RetryStrategy.EXPONENTIAL,
        nullable=False,
    )
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    initial_interval_sec: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    max_interval_sec: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    backoff_multiplier: Mapped[float] = mapped_column(Float, default=2.0, nullable=False)
    jitter: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now, nullable=False
    )

    # Relationships
    queue: Mapped["Queue"] = relationship("Queue", back_populates="retry_policy")
