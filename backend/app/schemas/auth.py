import uuid
from pydantic import BaseModel, EmailStr, Field
from backend.app.schemas.user import UserResponse, OrganizationResponse


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, description="User password (min 6 chars)")
    full_name: str = Field(..., min_length=2, description="User full name")
    organization_name: str = Field(..., min_length=2, description="Organization display name")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
    organization: OrganizationResponse
