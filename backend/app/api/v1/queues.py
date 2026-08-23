import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user, require_admin
from backend.app.models import User
from backend.app.schemas.queue import QueueUpdate, QueueResponse
from backend.app.services.queue_service import QueueService

router = APIRouter(prefix="/queues", tags=["Queues"])


@router.get(
    "/{queue_id}",
    response_model=QueueResponse,
    status_code=status.HTTP_200_OK,
    summary="Get queue configuration and live statistics",
)
async def get_queue(
    queue_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    queue = await QueueService.get_queue(db, current_user, queue_id)
    stats = await QueueService.get_queue_stats(db, queue_id, concurrency_limit=queue.concurrency_limit)
    resp = QueueResponse.model_validate(queue)
    resp.stats = stats
    return resp


@router.put(
    "/{queue_id}",
    response_model=QueueResponse,
    status_code=status.HTTP_200_OK,
    summary="Update queue settings (priority, concurrency, rate limit, retry policy)",
)
async def update_queue(
    queue_id: uuid.UUID,
    req: QueueUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await QueueService.update_queue(db, current_user, queue_id, req)


@router.post(
    "/{queue_id}/pause",
    response_model=QueueResponse,
    status_code=status.HTTP_200_OK,
    summary="Pause queue (workers immediately halt claiming new jobs from this queue)",
)
async def pause_queue(
    queue_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await QueueService.pause_queue(db, current_user, queue_id)


@router.post(
    "/{queue_id}/resume",
    response_model=QueueResponse,
    status_code=status.HTTP_200_OK,
    summary="Resume queue (workers resume claiming new jobs)",
)
async def resume_queue(
    queue_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await QueueService.resume_queue(db, current_user, queue_id)


@router.delete(
    "/{queue_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete queue and its associated jobs",
)
async def delete_queue(
    queue_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await QueueService.delete_queue(db, current_user, queue_id)
