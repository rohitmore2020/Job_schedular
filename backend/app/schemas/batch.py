import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.batch import BatchStatus
from backend.app.schemas.job import JobCreate, JobResponse


class BatchCreate(BaseModel):
    name: str = Field(..., max_length=255, description="Human-readable batch identifier")
    description: Optional[str] = Field(None, description="Optional batch description")
    jobs: List[JobCreate] = Field(..., min_length=1, max_length=5000, description="List of jobs in batch")


class BatchResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    queue_id: uuid.UUID
    name: str
    description: Optional[str] = None
    status: BatchStatus
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    cancelled_jobs: int
    pending_jobs: int
    progress_percent: float
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class BatchDetailResponse(BatchResponse):
    jobs: List[JobResponse] = []


class BatchListResponse(BaseModel):
    items: List[BatchResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
