import uuid
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from backend.app.models import Project, ProjectAPIKey, Queue, User
from backend.app.schemas.project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectAPIKeyCreate,
    ProjectAPIKeyWithSecretResponse,
    ProjectAPIKeyResponse,
)
from backend.app.services.auth_service import slugify


class ProjectService:
    @staticmethod
    async def list_projects(db: AsyncSession, user: User) -> List[ProjectResponse]:
        # Query projects with queue counts
        stmt = (
            select(
                Project,
                func.count(Queue.id).label("queues_count")
            )
            .outerjoin(Queue, Queue.project_id == Project.id)
            .where(Project.org_id == user.org_id)
            .group_by(Project.id)
            .order_by(Project.created_at.desc())
        )
        result = await db.execute(stmt)
        rows = result.all()

        projects_out = []
        for proj, count in rows:
            resp = ProjectResponse.model_validate(proj)
            resp.queues_count = count
            projects_out.append(resp)
        return projects_out

    @staticmethod
    async def get_project(db: AsyncSession, user: User, project_id: uuid.UUID) -> Project:
        stmt = select(Project).where(
            Project.id == project_id,
            Project.org_id == user.org_id
        )
        result = await db.execute(stmt)
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found or access denied",
            )
        return project

    @staticmethod
    async def create_project(db: AsyncSession, user: User, req: ProjectCreate) -> ProjectResponse:
        base_slug = slugify(req.slug or req.name)
        slug = f"{base_slug}-{uuid.uuid4().hex[:4]}"

        project = Project(
            org_id=user.org_id,
            name=req.name,
            slug=slug,
            description=req.description,
        )
        db.add(project)
        await db.commit()
        await db.refresh(project)

        resp = ProjectResponse.model_validate(project)
        resp.queues_count = 0
        return resp

    @staticmethod
    async def update_project(
        db: AsyncSession, user: User, project_id: uuid.UUID, req: ProjectUpdate
    ) -> ProjectResponse:
        project = await ProjectService.get_project(db, user, project_id)
        if req.name is not None:
            project.name = req.name
        if req.description is not None:
            project.description = req.description

        await db.commit()
        await db.refresh(project)
        return ProjectResponse.model_validate(project)

    @staticmethod
    async def create_api_key(
        db: AsyncSession, user: User, project_id: uuid.UUID, req: ProjectAPIKeyCreate
    ) -> ProjectAPIKeyWithSecretResponse:
        project = await ProjectService.get_project(db, user, project_id)

        # Generate secure random secret API key
        random_token = secrets.token_urlsafe(32)
        raw_key = f"cjs_live_{project.slug[:8]}_{random_token}"
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        prefix = f"cjs_live_{project.slug[:4]}..."

        expires_at = None
        if req.expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=req.expires_in_days)

        api_key = ProjectAPIKey(
            project_id=project.id,
            name=req.name,
            key_hash=key_hash,
            prefix=prefix,
            expires_at=expires_at,
        )
        db.add(api_key)
        await db.commit()
        await db.refresh(api_key)

        return ProjectAPIKeyWithSecretResponse(
            id=api_key.id,
            project_id=api_key.project_id,
            name=api_key.name,
            prefix=api_key.prefix,
            expires_at=api_key.expires_at,
            created_at=api_key.created_at,
            api_key=raw_key,
        )

    @staticmethod
    async def list_api_keys(
        db: AsyncSession, user: User, project_id: uuid.UUID
    ) -> List[ProjectAPIKeyResponse]:
        project = await ProjectService.get_project(db, user, project_id)
        stmt = (
            select(ProjectAPIKey)
            .where(ProjectAPIKey.project_id == project.id)
            .order_by(ProjectAPIKey.created_at.desc())
        )
        result = await db.execute(stmt)
        keys = result.scalars().all()
        return [ProjectAPIKeyResponse.model_validate(k) for k in keys]
