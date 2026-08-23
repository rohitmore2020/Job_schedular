import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from backend.app.models.enums import WorkerStatus


class WorkerHeartbeatResponse(BaseModel):
    id: int
    worker_id: str
    cpu_percent: float
    memory_mb: float
    active_jobs: int
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkerResponse(BaseModel):
    worker_id: str
    hostname: str
    pid: int
    concurrency_limit: int
    current_active_jobs: int
    status: WorkerStatus
    assigned_queues: List[str]
    started_at: datetime
    last_heartbeat_at: datetime
    is_alive: bool = True
    heartbeat_age_seconds: float = 0.0
    jobs_processed: int = 0
    failure_count: int = 0
    is_busy: bool = False
    is_idle: bool = True

    model_config = ConfigDict(from_attributes=True)
