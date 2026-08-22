import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, TYPE_CHECKING
from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from backend.app.core.database import Base

if TYPE_CHECKING:
    from backend.app.models.job import Job


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IdempotencyRecord(Base):
    """
    Stores idempotency execution records for external side effects and task operations.
    Enables tasks to achieve safe at-least-once execution with zero duplicate side effects.
    """
    __tablename__ = "idempotency_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(100), default="external_side_effect", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="completed", nullable=False)
    response_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False
    )

    # Relationships
    job: Mapped[Optional["Job"]] = relationship("Job")
