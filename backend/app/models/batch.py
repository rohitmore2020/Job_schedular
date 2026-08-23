import uuid
import enum
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from sqlalchemy import String, Integer, DateTime, ForeignKey, Enum as SQLEnum, Float, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from backend.app.core.database import Base

if TYPE_CHECKING:
    from backend.app.models.project import Project
    from backend.app.models.queue import Queue
    from backend.app.models.job import Job


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BatchStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIALLY_FAILED = "partially_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobBatch(Base):
    __tablename__ = "job_batches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    queue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[BatchStatus] = mapped_column(
        SQLEnum(BatchStatus, name="batch_status", values_callable=lambda x: [e.value for e in x], native_enum=True),
        default=BatchStatus.PROCESSING,
        nullable=False,
        index=True,
    )

    total_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cancelled_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project")
    queue: Mapped["Queue"] = relationship("Queue")
    jobs: Mapped[List["Job"]] = relationship(
        "Job", back_populates="batch", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def progress_percent(self) -> float:
        if not self.total_jobs or self.total_jobs == 0:
            return 100.0 if self.status == BatchStatus.COMPLETED else 0.0
        finished = self.completed_jobs + self.failed_jobs + self.cancelled_jobs
        return round((finished / self.total_jobs) * 100.0, 1)

    @property
    def pending_jobs(self) -> int:
        finished = self.completed_jobs + self.failed_jobs + self.cancelled_jobs
        return max(0, self.total_jobs - finished)
