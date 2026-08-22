import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user
from backend.app.models import User
from backend.app.schemas.schedule import (
    ScheduledJobCreate,
    ScheduledJobUpdate,
    ScheduledJobResponse,
)
from backend.app.services.schedule_service import ScheduleService

router = APIRouter(tags=["Schedules (Cron)"])


@router.post(
    "/queues/{queue_id}/schedules",
    response_model=ScheduledJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a recurring cron schedule for a queue",
)
async def create_schedule(
    queue_id: uuid.UUID,
    req: ScheduledJobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Define a cron-based recurring schedule (e.g. `*/10 * * * *`).
    """
    return await ScheduleService.create_schedule(db, current_user, queue_id, req)


@router.get(
    "/schedules",
    response_model=List[ScheduledJobResponse],
    status_code=status.HTTP_200_OK,
    summary="List recurring cron schedules",
)
async def list_schedules(
    project_id: Optional[uuid.UUID] = Query(None),
    queue_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve all scheduled recurring jobs with their next execution times.
    """
    return await ScheduleService.list_schedules(
        db, current_user, project_id=project_id, queue_id=queue_id
    )


@router.get(
    "/schedules/{schedule_id}",
    response_model=ScheduledJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Get recurring schedule details",
)
async def get_schedule(
    schedule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await ScheduleService.get_schedule(db, current_user, schedule_id)


@router.put(
    "/schedules/{schedule_id}",
    response_model=ScheduledJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Update recurring schedule",
)
async def update_schedule(
    schedule_id: uuid.UUID,
    req: ScheduledJobUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await ScheduleService.update_schedule(db, current_user, schedule_id, req)


@router.post(
    "/schedules/{schedule_id}/pause",
    response_model=ScheduledJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Pause a recurring schedule",
)
async def pause_schedule(
    schedule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await ScheduleService.pause_schedule(db, current_user, schedule_id)


@router.post(
    "/schedules/{schedule_id}/resume",
    response_model=ScheduledJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Resume a paused recurring schedule",
)
async def resume_schedule(
    schedule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await ScheduleService.resume_schedule(db, current_user, schedule_id)


@router.delete(
    "/schedules/{schedule_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a recurring schedule",
)
async def delete_schedule(
    schedule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await ScheduleService.delete_schedule(db, current_user, schedule_id)
