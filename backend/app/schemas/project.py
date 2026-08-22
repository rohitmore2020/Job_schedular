import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class ProjectBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255, description="Project display name")
    description: Optional[str] = Field(None, max_length=500, description="Project description")


class ProjectCreate(ProjectBase):
    slug: Optional[str] = Field(None, max_length=100, description="Optional custom URL slug")


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = Field(None, max_length=500)


class ProjectResponse(ProjectBase):
    id: uuid.UUID
    org_id: uuid.UUID
    slug: str
    created_at: datetime
    updated_at: datetime
    queues_count: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True)


class ProjectAPIKeyCreate(BaseModel):
    name: str = Field(default="Default API Key", max_length=100)
    expires_in_days: Optional[int] = Field(None, ge=1, le=365, description="Expiration in days")


class ProjectAPIKeyResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    prefix: str
    expires_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectAPIKeyWithSecretResponse(ProjectAPIKeyResponse):
    api_key: str = Field(..., description="Full secret API key (shown only once upon creation)")
