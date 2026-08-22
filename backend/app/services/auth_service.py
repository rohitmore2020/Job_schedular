import re
import uuid
from typing import Tuple, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from backend.app.models import Organization, User, Project, Queue, RetryPolicy, UserRole, RetryStrategy
from backend.app.schemas.auth import SignupRequest, LoginRequest, TokenResponse
from backend.app.schemas.user import UserResponse, OrganizationResponse
from backend.app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)


def slugify(text: str) -> str:
    """Convert text into URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text or "org"


class AuthService:
    @staticmethod
    async def signup(db: AsyncSession, req: SignupRequest) -> TokenResponse:
        # Check if email is already taken
        existing = await db.execute(select(User).where(User.email == req.email))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists",
            )

        # Generate unique slug for organization
        base_slug = slugify(req.organization_name)
        slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"

        # Create Organization
        org = Organization(name=req.organization_name, slug=slug)
        db.add(org)
        await db.flush()

        # Create Admin User
        hashed_pwd = hash_password(req.password)
        user = User(
            org_id=org.id,
            email=req.email,
            hashed_password=hashed_pwd,
            full_name=req.full_name,
            role=UserRole.ADMIN,
        )
        db.add(user)
        await db.flush()

        # Create Default Project and Default Queue for immediate usability
        default_proj = Project(
            org_id=org.id,
            name="Default Project",
            slug=f"default-{uuid.uuid4().hex[:4]}",
            description="Default project for asynchronous jobs",
        )
        db.add(default_proj)
        await db.flush()

        default_queue = Queue(
            project_id=default_proj.id,
            name="default",
            priority=10,
            concurrency_limit=10,
        )
        db.add(default_queue)
        await db.flush()

        default_retry = RetryPolicy(
            queue_id=default_queue.id,
            strategy=RetryStrategy.EXPONENTIAL,
            max_retries=3,
            initial_interval_sec=5,
            max_interval_sec=3600,
            backoff_multiplier=2.0,
            jitter=True,
        )
        db.add(default_retry)

        await db.commit()
        await db.refresh(user)
        await db.refresh(org)

        # Issue Tokens
        access_token = create_access_token(subject=user.id)
        refresh_token = create_refresh_token(subject=user.id)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=UserResponse.model_validate(user),
            organization=OrganizationResponse.model_validate(org),
        )

    @staticmethod
    async def login(db: AsyncSession, req: LoginRequest) -> TokenResponse:
        result = await db.execute(select(User).where(User.email == req.email))
        user = result.scalar_one_or_none()

        if not user or not verify_password(req.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        org_result = await db.execute(select(Organization).where(Organization.id == user.org_id))
        org = org_result.scalar_one()

        access_token = create_access_token(subject=user.id)
        refresh_token = create_refresh_token(subject=user.id)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=UserResponse.model_validate(user),
            organization=OrganizationResponse.model_validate(org),
        )

    @staticmethod
    async def refresh_token(db: AsyncSession, refresh_token_str: str) -> TokenResponse:
        payload = decode_token(refresh_token_str)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id_str = payload.get("sub")
        try:
            user_uuid = uuid.UUID(user_id_str)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed token subject",
            )

        result = await db.execute(select(User).where(User.id == user_uuid))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User no longer exists",
            )

        org_result = await db.execute(select(Organization).where(Organization.id == user.org_id))
        org = org_result.scalar_one()

        new_access_token = create_access_token(subject=user.id)
        new_refresh_token = create_refresh_token(subject=user.id)

        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            user=UserResponse.model_validate(user),
            organization=OrganizationResponse.model_validate(org),
        )
