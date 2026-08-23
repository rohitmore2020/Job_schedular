import uuid
from typing import List, Optional, Dict
from pydantic import BaseModel, ConfigDict


class SystemTelemetry(BaseModel):
    total_jobs: int = 0
    queued_jobs: int = 0
    running_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    dead_letter_jobs: int = 0
    cancelled_jobs: int = 0
    jobs_per_sec: float = 0.0
    success_rate_percent: float = 0.0
    failure_rate_percent: float = 0.0
    retry_rate_percent: float = 0.0
    dlq_rate_percent: float = 0.0


class QueueTelemetry(BaseModel):
    queue_id: uuid.UUID
    queue_name: str
    priority: int
    concurrency_limit: int
    is_paused: bool
    queue_depth: int = 0
    running_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    dead_letter_jobs: int = 0
    concurrency_utilization_percent: float = 0.0
    oldest_job_age_seconds: Optional[float] = None
    average_wait_time_ms: Optional[float] = None
    throughput_jobs_per_sec: float = 0.0


class WorkerFleetTelemetry(BaseModel):
    workers_online: int = 0
    workers_busy: int = 0
    workers_idle: int = 0
    total_active_jobs: int = 0
    average_cpu_percent: float = 0.0
    average_memory_mb: float = 0.0


class FullTelemetryResponse(BaseModel):
    system: SystemTelemetry
    fleet: WorkerFleetTelemetry
    queues: List[QueueTelemetry]
    timestamp: str
