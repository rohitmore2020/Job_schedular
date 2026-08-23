import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user, require_developer_or_admin
from backend.app.models import User
from backend.app.schemas.dlq import (
    DLQEntryDetailResponse,
    DLQListResponse,
    DLQReplayResponse,
)
from backend.app.services.dlq_service import DLQService

router = APIRouter(tags=["Dead Letter Queue"])


@router.get(
    "/queues/{queue_id}/dlq",
    response_model=DLQListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Dead Letter Queue entries for a queue",
)
async def list_queue_dlq(
    queue_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve paginated dead-lettered jobs with stack traces and failure reasons.
    """
    return await DLQService.list_dlq_entries(
        db, current_user, queue_id=queue_id, page=page, page_size=page_size
    )


@router.get(
    "/dlq/{dlq_id}",
    response_model=DLQEntryDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single DLQ entry detail",
)
async def get_dlq_entry(
    dlq_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Inspect a specific DLQ incident including original payload, stack trace, and attempt count.
    """
    return await DLQService.get_dlq_entry(db, current_user, dlq_id)


@router.post(
    "/dlq/{dlq_id}/replay",
    response_model=DLQReplayResponse,
    status_code=status.HTTP_200_OK,
    summary="Replay/Redrive a dead-lettered job back into the ready queue",
)
async def replay_dlq_entry(
    dlq_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_developer_or_admin),
):
    """
    Re-enqueue an unrecoverable job back to `queued` status for immediate re-execution.
    """
    return await DLQService.replay_dlq_entry(db, current_user, dlq_id)


@router.post(
    "/queues/{queue_id}/dlq/replay-all",
    response_model=DLQReplayResponse,
    status_code=status.HTTP_200_OK,
    summary="Bulk redrive all pending DLQ jobs in a queue",
)
async def replay_all_dlq_entries(
    queue_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_developer_or_admin),
):
    """
    Bulk replay all active DLQ items in a queue back into the active ready queue.
    """
    return await DLQService.replay_all_dlq_entries(db, current_user, queue_id)


@router.delete(
    "/dlq/{dlq_id}",
    status_code=status.HTTP_200_OK,
    summary="Permanently purge a DLQ entry",
)
async def purge_dlq_entry(
    dlq_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_developer_or_admin),
):
    """
    Purge a dead-letter record after resolution.
    """
    return await DLQService.purge_dlq_entry(db, current_user, dlq_id)
