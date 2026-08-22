from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user
from backend.app.models import User, Organization
from backend.app.schemas.auth import (
    SignupRequest,
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
)
from backend.app.schemas.user import UserResponse, OrganizationResponse
from backend.app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new organization and admin user",
)
async def signup(
    req: SignupRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new Organization, Admin User account, and initialize a default project & queue.
    Returns JWT access + refresh tokens.
    """
    return await AuthService.signup(db, req)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate with email and password",
)
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate an existing user by email and password.
    Returns JWT access and refresh token pair.
    """
    return await AuthService.login(db, req)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate refresh token for new access token",
)
async def refresh_token(
    req: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Provide a valid refresh token to receive a fresh access and refresh token pair.
    """
    return await AuthService.refresh_token(db, req.refresh_token)


@router.get(
    "/me",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Get profile of currently logged-in user",
)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve profile details and organization of the authenticated user.
    """
    org_res = await db.execute(
        select(Organization).where(Organization.id == current_user.org_id)
    )
    org = org_res.scalar_one()

    return {
        "user": UserResponse.model_validate(current_user),
        "organization": OrganizationResponse.model_validate(org),
    }
