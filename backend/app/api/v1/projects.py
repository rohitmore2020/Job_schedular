import uuid
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user, require_admin
from backend.app.models import User
from backend.app.schemas.project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectAPIKeyCreate,
    ProjectAPIKeyResponse,
    ProjectAPIKeyWithSecretResponse,
)
from backend.app.schemas.queue import QueueCreate, QueueResponse
from backend.app.services.project_service import ProjectService
from backend.app.services.queue_service import QueueService

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get(
    "",
    response_model=List[ProjectResponse],
    status_code=status.HTTP_200_OK,
    summary="List all projects owned by the user's organization",
)
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await ProjectService.list_projects(db, current_user)


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
)
async def create_project(
    req: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await ProjectService.create_project(db, current_user, req)


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Get project by ID",
)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await ProjectService.get_project(db, current_user, project_id)
    resp = ProjectResponse.model_validate(project)
    queues = await QueueService.list_queues(db, current_user, project_id)
    resp.queues_count = len(queues)
    return resp


@router.put(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Update project details",
)
async def update_project(
    project_id: uuid.UUID,
    req: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await ProjectService.update_project(db, current_user, project_id, req)


@router.post(
    "/{project_id}/api-keys",
    response_model=ProjectAPIKeyWithSecretResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a new API key for the project",
)
async def create_api_key(
    project_id: uuid.UUID,
    req: ProjectAPIKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await ProjectService.create_api_key(db, current_user, project_id, req)


@router.get(
    "/{project_id}/api-keys",
    response_model=List[ProjectAPIKeyResponse],
    status_code=status.HTTP_200_OK,
    summary="List API keys for the project",
)
async def list_api_keys(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await ProjectService.list_api_keys(db, current_user, project_id)


@router.get(
    "/{project_id}/queues",
    response_model=List[QueueResponse],
    status_code=status.HTTP_200_OK,
    summary="List all queues in this project with live statistics",
)
async def list_project_queues(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await QueueService.list_queues(db, current_user, project_id)


@router.post(
    "/{project_id}/queues",
    response_model=QueueResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new job queue in this project",
)
async def create_project_queue(
    project_id: uuid.UUID,
    req: QueueCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await QueueService.create_queue(db, current_user, project_id, req)
