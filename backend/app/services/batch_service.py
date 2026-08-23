import uuid
import math
from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy import select, func, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from backend.app.models import (
    User,
    Project,
    Queue,
    Job,
    JobBatch,
    BatchStatus,
    JobStatus,
)
from backend.app.schemas.batch import BatchCreate


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BatchService:
    @staticmethod
    async def create_batch(
        db: AsyncSession, user: User, queue_id: uuid.UUID, data: BatchCreate
    ) -> JobBatch:
        """Atomically create a JobBatch and enqueue all its child jobs."""
        # 1. Verify queue and tenant access
        queue_stmt = select(Queue).where(Queue.id == queue_id)
        queue_res = await db.execute(queue_stmt)
        queue = queue_res.scalar_one_or_none()
        if not queue:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Queue '{queue_id}' not found",
            )

        proj_stmt = select(Project).where(
            Project.id == queue.project_id,
            Project.org_id == user.org_id,
        )
        proj_res = await db.execute(proj_stmt)
        if not proj_res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access to queue forbidden",
            )

        now_utc = get_utc_now()
        total_jobs = len(data.jobs)
        batch_id = uuid.uuid4()

        # 2. Create JobBatch record
        batch = JobBatch(
            id=batch_id,
            project_id=queue.project_id,
            queue_id=queue.id,
            name=data.name,
            description=data.description,
            status=BatchStatus.PROCESSING,
            total_jobs=total_jobs,
            completed_jobs=0,
            failed_jobs=0,
            cancelled_jobs=0,
            created_at=now_utc,
            updated_at=now_utc,
        )
        db.add(batch)
        await db.flush()

        # 3. Create all child jobs stamped with batch_id
        for item in data.jobs:
            job_run_at = item.run_at or now_utc
            job_status = JobStatus.SCHEDULED if job_run_at > now_utc else JobStatus.QUEUED

            job = Job(
                id=uuid.uuid4(),
                queue_id=queue.id,
                batch_id=batch_id,
                idempotency_key=item.idempotency_key,
                name=item.name,
                status=job_status,
                priority=item.priority,
                payload=item.payload,
                max_retries=item.max_retries,
                run_at=job_run_at,
                tags=item.tags,
                parent_job_id=item.parent_job_id,
                created_at=now_utc,
                updated_at=now_utc,
            )
            db.add(job)

        await db.commit()

        # Reload batch with jobs
        return await BatchService.get_batch(db, user, batch_id)

    @staticmethod
    async def get_batch(
        db: AsyncSession, user: User, batch_id: uuid.UUID
    ) -> JobBatch:
        """Fetch batch details with permission check and refreshed counters."""
        stmt = (
            select(JobBatch)
            .join(Project, JobBatch.project_id == Project.id)
            .where(
                JobBatch.id == batch_id,
                Project.org_id == user.org_id,
            )
        )
        res = await db.execute(stmt)
        batch = res.scalar_one_or_none()
        if not batch:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Batch '{batch_id}' not found",
            )

        # Refresh aggregated counters from jobs table
        counter_stmt = select(
            func.count(Job.id).filter(Job.status == JobStatus.COMPLETED).label("completed"),
            func.count(Job.id).filter(Job.status.in_([JobStatus.DEAD_LETTER, JobStatus.FAILED])).label("failed"),
            func.count(Job.id).filter(Job.status == JobStatus.CANCELLED).label("cancelled"),
        ).where(Job.batch_id == batch_id)
        c_res = await db.execute(counter_stmt)
        c_row = c_res.fetchone()
        if c_row:
            batch.completed_jobs = c_row.completed or 0
            batch.failed_jobs = c_row.failed or 0
            batch.cancelled_jobs = c_row.cancelled or 0

            finished = batch.completed_jobs + batch.failed_jobs + batch.cancelled_jobs
            if batch.status != BatchStatus.CANCELLED and finished >= batch.total_jobs and batch.total_jobs > 0:
                if batch.failed_jobs == 0 and batch.cancelled_jobs == 0:
                    batch.status = BatchStatus.COMPLETED
                elif batch.completed_jobs > 0:
                    batch.status = BatchStatus.PARTIALLY_FAILED
                elif batch.cancelled_jobs == batch.total_jobs:
                    batch.status = BatchStatus.CANCELLED
                else:
                    batch.status = BatchStatus.FAILED
                if not batch.completed_at:
                    batch.completed_at = get_utc_now()

        return batch

    @staticmethod
    async def list_batches(
        db: AsyncSession,
        user: User,
        project_id: Optional[uuid.UUID] = None,
        queue_id: Optional[uuid.UUID] = None,
        batch_status: Optional[BatchStatus] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[JobBatch], int, int]:
        """List paginated batches with tenant isolation."""
        query = (
            select(JobBatch)
            .join(Project, JobBatch.project_id == Project.id)
            .where(Project.org_id == user.org_id)
        )
        count_query = (
            select(func.count(JobBatch.id))
            .join(Project, JobBatch.project_id == Project.id)
            .where(Project.org_id == user.org_id)
        )

        if project_id:
            query = query.where(JobBatch.project_id == project_id)
            count_query = count_query.where(JobBatch.project_id == project_id)
        if queue_id:
            query = query.where(JobBatch.queue_id == queue_id)
            count_query = count_query.where(JobBatch.queue_id == queue_id)
        if batch_status:
            query = query.where(JobBatch.status == batch_status)
            count_query = count_query.where(JobBatch.status == batch_status)

        count_res = await db.execute(count_query)
        total = count_res.scalar_one()

        total_pages = math.ceil(total / page_size) if total > 0 else 1
        offset = (page - 1) * page_size

        query = query.order_by(JobBatch.created_at.desc()).offset(offset).limit(page_size)
        res = await db.execute(query)
        batches = res.scalars().all()

        return list(batches), total, total_pages

    @staticmethod
    async def cancel_batch(
        db: AsyncSession, user: User, batch_id: uuid.UUID
    ) -> JobBatch:
        """Cancel all pending and queued jobs in a batch."""
        batch = await BatchService.get_batch(db, user, batch_id)

        # Cancel any pending/queued/scheduled jobs in this batch
        now_utc = get_utc_now()
        cancel_stmt = (
            update(Job)
            .where(
                Job.batch_id == batch_id,
                Job.status.in_([JobStatus.QUEUED, JobStatus.SCHEDULED]),
            )
            .values(status=JobStatus.CANCELLED, updated_at=now_utc)
        )
        await db.execute(cancel_stmt)

        batch.status = BatchStatus.CANCELLED
        batch.updated_at = now_utc
        await db.commit()
        await db.refresh(batch)

        return await BatchService.get_batch(db, user, batch_id)

    @staticmethod
    async def retry_batch(
        db: AsyncSession, user: User, batch_id: uuid.UUID
    ) -> JobBatch:
        """Re-enqueue all failed or cancelled jobs in a batch."""
        batch = await BatchService.get_batch(db, user, batch_id)

        now_utc = get_utc_now()
        retry_stmt = (
            update(Job)
            .where(
                Job.batch_id == batch_id,
                Job.status.in_([JobStatus.DEAD_LETTER, JobStatus.FAILED, JobStatus.CANCELLED]),
            )
            .values(
                status=JobStatus.QUEUED,
                attempt_count=0,
                error_message=None,
                run_at=now_utc,
                updated_at=now_utc,
            )
        )
        await db.execute(retry_stmt)

        batch.status = BatchStatus.PROCESSING
        batch.completed_at = None
        batch.updated_at = now_utc
        await db.commit()
        await db.refresh(batch)

        return await BatchService.get_batch(db, user, batch_id)
