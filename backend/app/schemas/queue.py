import uuid
from datetime import datetime
from typing import Optional, Dict
from pydantic import BaseModel, Field, ConfigDict
from backend.app.models.enums import RetryStrategy


class RetryPolicyBase(BaseModel):
    strategy: RetryStrategy = Field(default=RetryStrategy.EXPONENTIAL, description="Retry strategy: fixed, linear, exponential")
    max_retries: int = Field(default=3, ge=0, le=20, description="Max retry attempts")
    initial_interval_sec: int = Field(default=5, ge=1, le=86400, description="Initial retry interval in seconds")
    max_interval_sec: int = Field(default=3600, ge=1, le=86400, description="Max backoff ceiling in seconds")
    backoff_multiplier: float = Field(default=2.0, ge=1.0, le=10.0, description="Multiplier for exponential backoff")
    jitter: bool = Field(default=True, description="Add randomized jitter to avoid thundering herd")


class RetryPolicyCreate(RetryPolicyBase):
    pass


class RetryPolicyUpdate(BaseModel):
    strategy: Optional[RetryStrategy] = None
    max_retries: Optional[int] = Field(None, ge=0, le=20)
    initial_interval_sec: Optional[int] = Field(None, ge=1, le=86400)
    max_interval_sec: Optional[int] = Field(None, ge=1, le=86400)
    backoff_multiplier: Optional[float] = Field(None, ge=1.0, le=10.0)
    jitter: Optional[bool] = None


class RetryPolicyResponse(RetryPolicyBase):
    id: uuid.UUID
    queue_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class QueueBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$", description="Queue identifier")
    priority: int = Field(default=10, ge=1, le=100, description="Priority score 1-100 (higher = claims earlier)")
    concurrency_limit: int = Field(default=10, ge=1, le=1000, description="Maximum concurrent active jobs")
    rate_limit_rps: Optional[int] = Field(None, ge=1, le=10000, description="Optional rate limit per second")


class QueueCreate(QueueBase):
    retry_policy: Optional[RetryPolicyCreate] = None


class QueueUpdate(BaseModel):
    priority: Optional[int] = Field(None, ge=1, le=100)
    concurrency_limit: Optional[int] = Field(None, ge=1, le=1000)
    rate_limit_rps: Optional[int] = Field(None, ge=1, le=10000)
    retry_policy: Optional[RetryPolicyUpdate] = None


class QueueStats(BaseModel):
    queued: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    dead_letter: int = 0
    total: int = 0


class QueueResponse(QueueBase):
    id: uuid.UUID
    project_id: uuid.UUID
    is_paused: bool
    created_at: datetime
    updated_at: datetime
    retry_policy: Optional[RetryPolicyResponse] = None
    stats: Optional[QueueStats] = None

    model_config = ConfigDict(from_attributes=True)
