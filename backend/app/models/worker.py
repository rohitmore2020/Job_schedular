from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import String, Integer, Float, DateTime, Enum as SQLEnum, ForeignKey, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from backend.app.core.database import Base
from backend.app.models.enums import WorkerStatus


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Worker(Base):
    __tablename__ = "workers"

    worker_id: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    pid: Mapped[int] = mapped_column(Integer, nullable=False)
    concurrency_limit: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    current_active_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[WorkerStatus] = mapped_column(
        SQLEnum(WorkerStatus, values_callable=lambda x: [e.value for e in x], native_enum=True),
        default=WorkerStatus.ALIVE,
        nullable=False,
        index=True,
    )
    assigned_queues: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now, nullable=False
    )
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now, nullable=False, index=True
    )

    # Relationships
    heartbeats: Mapped[List["WorkerHeartbeat"]] = relationship(
        "WorkerHeartbeat", back_populates="worker", cascade="all, delete-orphan", order_by="desc(WorkerHeartbeat.timestamp)"
    )


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    worker_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("workers.worker_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cpu_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    memory_mb: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    active_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now, nullable=False, index=True
    )

    # Relationships
    worker: Mapped["Worker"] = relationship("Worker", back_populates="heartbeats")
