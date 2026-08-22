import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from backend.app.schemas.job import JobResponse


class DLQEntryDetailResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    queue_id: uuid.UUID
    failed_reason: str
    total_attempts: int
    last_error: Optional[str] = None
    ai_failure_summary: Optional[str] = None
    moved_to_dlq_at: datetime
    is_replayed: bool
    replayed_at: Optional[datetime] = None
    job: Optional[JobResponse] = None

    model_config = ConfigDict(from_attributes=True)


class DLQListResponse(BaseModel):
    items: List[DLQEntryDetailResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class DLQReplayResponse(BaseModel):
    message: str
    replayed_count: int
    job_ids: List[uuid.UUID]
