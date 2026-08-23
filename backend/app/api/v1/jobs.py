import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user, require_developer_or_admin
from backend.app.models import User, JobStatus
from backend.app.schemas.job import (
    JobCreate,
    JobBatchCreate,
    JobResponse,
    JobDetailResponse,
    JobExecutionResponse,
    JobListResponse,
)
from backend.app.services.job_service import JobService

router = APIRouter(tags=["Jobs"])


@router.post(
    "/queues/{queue_id}/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a job to a queue (Immediate or Delayed)",
)
async def create_job(
    queue_id: uuid.UUID,
    req: JobCreate,
    idempotency_key_header: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_developer_or_admin),
):
    """
    Enqueue a background job with payload, priority, and optional scheduled execution time.
    Supports atomic client idempotency deduplication via `Idempotency-Key` header or payload.
    """
    return await JobService.create_job(
        db, current_user, queue_id, req, header_idempotency_key=idempotency_key_header
    )


@router.post(
    "/queues/{queue_id}/jobs/batch",
    response_model=List[JobResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Batch submit up to 1000 jobs in a single atomic transaction",
)
async def create_jobs_batch(
    queue_id: uuid.UUID,
    req: JobBatchCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_developer_or_admin),
):
    """
    Submit up to 1,000 background jobs in a single bulk database transaction.
    """
    return await JobService.create_jobs_batch(db, current_user, queue_id, req)


@router.get(
    "/jobs",
    response_model=JobListResponse,
    status_code=status.HTTP_200_OK,
    summary="List and filter jobs across queues and projects",
)
async def list_jobs(
    project_id: Optional[uuid.UUID] = Query(None, description="Filter by project"),
    queue_id: Optional[uuid.UUID] = Query(None, description="Filter by queue"),
    status: Optional[JobStatus] = Query(None, description="Filter by job lifecycle status"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    search: Optional[str] = Query(None, description="Search by job name or idempotency key"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve paginated jobs with search and filtering by status, queue, or tag.
    """
    return await JobService.list_jobs(
        db,
        current_user,
        project_id=project_id,
        queue_id=queue_id,
        status_filter=status,
        tag=tag,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get job details with execution trace timeline",
)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Inspect job state, execution logs, attempt metrics, and Dead Letter Queue info.
    """
    return await JobService.get_job(db, current_user, job_id)


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=JobResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel a queued, scheduled, or running job",
)
async def cancel_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_developer_or_admin),
):
    """
    Cancel an in-flight, queued, or scheduled job.
    """
    return await JobService.cancel_job(db, current_user, job_id)


@router.post(
    "/jobs/{job_id}/retry",
    response_model=JobResponse,
    status_code=status.HTTP_200_OK,
    summary="Manually re-enqueue a failed or cancelled job",
)
async def retry_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_developer_or_admin),
):
    """
    Reset and re-enqueue a failed, cancelled, or DLQ job for immediate re-execution.
    """
    return await JobService.retry_job(db, current_user, job_id)


@router.get(
    "/jobs/{job_id}/logs",
    response_model=List[JobExecutionResponse],
    status_code=status.HTTP_200_OK,
    summary="Get execution logs for a job",
)
async def get_job_logs(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve stdout/stderr logs and stack traces from all execution attempts.
    """
    return await JobService.get_job_logs(db, current_user, job_id)
