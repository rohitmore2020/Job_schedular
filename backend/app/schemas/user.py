import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict
from backend.app.models.enums import UserRole


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: UserRole = UserRole.MEMBER


class UserCreate(UserBase):
    password: str
    org_name: str


class UserResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
