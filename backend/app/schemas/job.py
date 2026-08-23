import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from backend.app.models.enums import JobStatus, ExecutionStatus


class JobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Task identifier name")
    payload: Dict[str, Any] = Field(default_factory=dict, description="JSON input arguments")
    priority: int = Field(default=10, ge=1, le=100, description="Priority score 1-100 (higher = claims first)")
    max_retries: int = Field(default=3, ge=0, le=20, description="Max retry attempts before moving to DLQ")
    run_at: Optional[datetime] = Field(None, description="Earliest execution time (UTC)")
    delay_seconds: Optional[int] = Field(None, ge=0, description="Delay execution by N seconds from now")
    idempotency_key: Optional[str] = Field(None, max_length=255, description="Client idempotency key")
    parent_job_id: Optional[uuid.UUID] = Field(None, description="Parent job UUID for workflow DAGs")
    tags: List[str] = Field(default_factory=list, description="Categorization tags")


class JobBatchCreate(BaseModel):
    jobs: List[JobCreate] = Field(..., min_length=1, max_length=1000, description="List of jobs to submit (max 1000)")


class JobExecutionResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    worker_id: str
    attempt_number: int
    status: ExecutionStatus
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None
    logs: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DLQEntryResponse(BaseModel):
    id: uuid.UUID
    failed_reason: str
    total_attempts: int
    last_error: Optional[str] = None
    ai_failure_summary: Optional[str] = None
    moved_to_dlq_at: datetime
    is_replayed: bool
    replayed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class JobResponse(BaseModel):
    id: uuid.UUID
    queue_id: uuid.UUID
    idempotency_key: Optional[str] = None
    name: str
    status: JobStatus
    priority: int
    payload: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    attempt_count: int
    max_retries: int
    run_at: datetime
    claimed_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    locked_by_worker_id: Optional[str] = None
    lease_token: Optional[uuid.UUID] = None
    lock_expires_at: Optional[datetime] = None
    parent_job_id: Optional[uuid.UUID] = None
    batch_id: Optional[uuid.UUID] = None
    tags: List[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JobDetailResponse(JobResponse):
    executions: List[JobExecutionResponse] = []
    dlq_entry: Optional[DLQEntryResponse] = None


class JobListResponse(BaseModel):
    items: List[JobResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
