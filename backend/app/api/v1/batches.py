import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user, require_developer_or_admin
from backend.app.models import User, Job, JobStatus, BatchStatus
from backend.app.schemas.batch import (
    BatchCreate,
    BatchResponse,
    BatchDetailResponse,
    BatchListResponse,
)
from backend.app.schemas.job import JobListResponse, JobResponse
from backend.app.services.batch_service import BatchService

router = APIRouter(tags=["Batches"])


@router.post(
    "/queues/{queue_id}/batches",
    response_model=BatchDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a batch of jobs",
)
async def create_batch(
    queue_id: uuid.UUID,
    data: BatchCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_developer_or_admin),
):
    """Atomically create a JobBatch and enqueue all its child jobs."""
    batch = await BatchService.create_batch(db, current_user, queue_id, data)
    return batch


@router.get(
    "/batches",
    response_model=BatchListResponse,
    summary="List all batches",
)
async def list_batches(
    project_id: Optional[uuid.UUID] = Query(None, description="Filter by project ID"),
    queue_id: Optional[uuid.UUID] = Query(None, description="Filter by queue ID"),
    batch_status: Optional[BatchStatus] = Query(None, alias="status", description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List paginated batches with live progress metrics."""
    batches, total, total_pages = await BatchService.list_batches(
        db, current_user, project_id, queue_id, batch_status, page, page_size
    )
    return BatchListResponse(
        items=batches,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/batches/{batch_id}",
    response_model=BatchDetailResponse,
    summary="Get batch details and live progress",
)
async def get_batch(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get detailed batch status with live completion percentage and child jobs."""
    return await BatchService.get_batch(db, current_user, batch_id)


@router.get(
    "/batches/{batch_id}/jobs",
    response_model=JobListResponse,
    summary="List jobs in a batch",
)
async def get_batch_jobs(
    batch_id: uuid.UUID,
    job_status: Optional[JobStatus] = Query(None, alias="status", description="Filter by job status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List child jobs of a batch with pagination and status filter."""
    await BatchService.get_batch(db, current_user, batch_id)

    query = select(Job).where(Job.batch_id == batch_id)
    if job_status:
        query = query.where(Job.status == job_status)

    count_stmt = select(Job.id).where(Job.batch_id == batch_id)
    if job_status:
        count_stmt = count_stmt.where(Job.status == job_status)
    c_res = await db.execute(count_stmt)
    total = len(c_res.scalars().all())

    offset = (page - 1) * page_size
    query = query.order_by(Job.created_at.asc()).offset(offset).limit(page_size)
    res = await db.execute(query)
    jobs = res.scalars().all()

    import math
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return JobListResponse(
        items=list(jobs),
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post(
    "/batches/{batch_id}/cancel",
    response_model=BatchResponse,
    summary="Cancel all pending jobs in a batch",
)
async def cancel_batch(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_developer_or_admin),
):
    """Cancel all pending/queued jobs in a batch."""
    return await BatchService.cancel_batch(db, current_user, batch_id)


@router.post(
    "/batches/{batch_id}/retry",
    response_model=BatchResponse,
    summary="Retry all failed jobs in a batch",
)
async def retry_batch(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_developer_or_admin),
):
    """Re-enqueue all failed/DLQ jobs in a batch."""
    return await BatchService.retry_batch(db, current_user, batch_id)
