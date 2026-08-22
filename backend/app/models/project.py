import uuid
from datetime import datetime, timezone
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from backend.app.core.database import Base

if TYPE_CHECKING:
    from backend.app.models.organization import Organization
    from backend.app.models.queue import Queue
    from backend.app.models.schedule import ScheduledJob


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_project_org_slug"),
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="projects")
    queues: Mapped[List["Queue"]] = relationship(
        "Queue", back_populates="project", cascade="all, delete-orphan"
    )
    api_keys: Mapped[List["ProjectAPIKey"]] = relationship(
        "ProjectAPIKey", back_populates="project", cascade="all, delete-orphan"
    )
    scheduled_jobs: Mapped[List["ScheduledJob"]] = relationship(
        "ScheduledJob", back_populates="project", cascade="all, delete-orphan"
    )


class ProjectAPIKey(Base):
    __tablename__ = "project_api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="Default API Key")
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now, nullable=False
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="api_keys")
