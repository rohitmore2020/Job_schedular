import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict, field_validator
from croniter import croniter


class ScheduledJobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Schedule name / task identifier")
    cron_expression: str = Field(..., description="Standard 5-part cron syntax (e.g. '*/5 * * * *')")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Job payload to pass to each execution")
    priority: int = Field(default=10, ge=1, le=100)
    timezone: str = Field(default="UTC", description="Timezone name")

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        if not croniter.is_valid(v):
            raise ValueError(f"Invalid cron expression: '{v}'. Must be standard 5-part cron syntax (e.g. '*/10 * * * *')")
        return v


class ScheduledJobUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    cron_expression: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    priority: Optional[int] = Field(None, ge=1, le=100)
    is_active: Optional[bool] = None

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not croniter.is_valid(v):
            raise ValueError(f"Invalid cron expression: '{v}'")
        return v


class ScheduledJobResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    queue_id: uuid.UUID
    name: str
    cron_expression: str
    payload: Dict[str, Any]
    priority: int
    is_active: bool
    last_run_at: Optional[datetime] = None
    next_run_at: datetime
    total_runs_count: int = 0
    timezone: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
