import uuid
import math
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from sqlalchemy import select, func, desc, or_, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from backend.app.models import Job, JobExecution, DLQEntry, Queue, Project, User, JobStatus
from backend.app.schemas.job import (
    JobCreate,
    JobBatchCreate,
    JobResponse,
    JobDetailResponse,
    JobExecutionResponse,
    JobListResponse,
)
from backend.app.services.queue_service import QueueService


class JobService:
    @staticmethod
    async def create_job(
        db: AsyncSession,
        user: User,
        queue_id: uuid.UUID,
        req: JobCreate,
        header_idempotency_key: Optional[str] = None,
    ) -> JobResponse:
        queue = await QueueService.get_queue(db, user, queue_id)
        target_queue_id = queue.id

        idempotency_key = req.idempotency_key or header_idempotency_key

        # 1. Fast path: check if idempotency key already exists in DB
        if idempotency_key:
            stmt = select(Job).where(
                Job.queue_id == target_queue_id,
                Job.idempotency_key == idempotency_key,
            )
            result = await db.execute(stmt)
            existing_job = result.scalar_one_or_none()
            if existing_job:
                return JobResponse.model_validate(existing_job)

        # 2. Compute execution schedule & DAG parent resolution
        now_utc = datetime.now(timezone.utc)
        run_at = now_utc
        if req.delay_seconds is not None and req.delay_seconds > 0:
            run_at = now_utc + timedelta(seconds=req.delay_seconds)
        elif req.run_at is not None:
            run_at = req.run_at

        # Determine initial status
        initial_status = JobStatus.SCHEDULED if run_at > now_utc + timedelta(seconds=2) else JobStatus.QUEUED

        # ⛓️ DAG Workflow parent dependency check
        if req.parent_job_id:
            parent_stmt = select(Job).where(Job.id == req.parent_job_id)
            parent_res = await db.execute(parent_stmt)
            parent_job = parent_res.scalar_one_or_none()
            if not parent_job:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Parent DAG job {req.parent_job_id} does not exist",
                )
            if parent_job.status in (JobStatus.DEAD_LETTER, JobStatus.CANCELLED):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot chain child task to parent in '{parent_job.status.value}' state",
                )
            if parent_job.status != JobStatus.COMPLETED:
                # Parent still in progress -> Child must wait in SCHEDULED state
                initial_status = JobStatus.SCHEDULED
                run_at = datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
            else:
                # Parent already finished -> Child can run immediately
                initial_status = JobStatus.QUEUED
                run_at = now_utc

        # 3. Atomic INSERT with ON CONFLICT (queue_id, idempotency_key) DO NOTHING
        if idempotency_key:
            job_id = uuid.uuid4()
            insert_stmt = (
                pg_insert(Job)
                .values(
                    id=job_id,
                    queue_id=target_queue_id,
                    idempotency_key=idempotency_key,
                    name=req.name,
                    status=initial_status,
                    priority=req.priority,
                    payload=req.payload,
                    max_retries=req.max_retries,
                    run_at=run_at,
                    parent_job_id=req.parent_job_id,
                    tags=req.tags,
                    created_at=now_utc,
                    updated_at=now_utc,
                )
                .on_conflict_do_nothing(
                    index_elements=["queue_id", "idempotency_key"],
                    index_where=text("idempotency_key IS NOT NULL"),
                )
                .returning(Job.id)
            )
            try:
                res_insert = await db.execute(insert_stmt)
                row = res_insert.fetchone()
                if row:
                    await db.commit()
                    stmt = select(Job).where(Job.id == row[0])
                    res = await db.execute(stmt)
                    job = res.scalar_one()
                    return JobResponse.model_validate(job)
                else:
                    # Conflict occurred (another concurrent transaction inserted same key)
                    await db.rollback()
                    stmt = select(Job).where(
                        Job.queue_id == target_queue_id,
                        Job.idempotency_key == idempotency_key,
                    )
                    res = await db.execute(stmt)
                    existing_job = res.scalar_one()
                    return JobResponse.model_validate(existing_job)
            except Exception:
                await db.rollback()
                stmt = select(Job).where(
                    Job.queue_id == target_queue_id,
                    Job.idempotency_key == idempotency_key,
                )
                res = await db.execute(stmt)
                existing_job = res.scalar_one()
                return JobResponse.model_validate(existing_job)
        else:
            job = Job(
                queue_id=target_queue_id,
                idempotency_key=None,
                name=req.name,
                status=initial_status,
                priority=req.priority,
                payload=req.payload,
                max_retries=req.max_retries,
                run_at=run_at,
                parent_job_id=req.parent_job_id,
                tags=req.tags,
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)
            return JobResponse.model_validate(job)

    @staticmethod
    async def create_jobs_batch(
        db: AsyncSession,
        user: User,
        queue_id: uuid.UUID,
        req: JobBatchCreate,
    ) -> List[JobResponse]:
        queue = await QueueService.get_queue(db, user, queue_id)
        target_queue_id = queue.id

        now_utc = datetime.now(timezone.utc)
        resolved_job_ids = []

        for item in req.jobs:
            run_at = now_utc
            if item.delay_seconds is not None and item.delay_seconds > 0:
                run_at = now_utc + timedelta(seconds=item.delay_seconds)
            elif item.run_at is not None:
                run_at = item.run_at

            initial_status = JobStatus.SCHEDULED if run_at > now_utc + timedelta(seconds=2) else JobStatus.QUEUED

            if item.idempotency_key:
                insert_stmt = (
                    pg_insert(Job)
                    .values(
                        id=uuid.uuid4(),
                        queue_id=target_queue_id,
                        idempotency_key=item.idempotency_key,
                        name=item.name,
                        status=initial_status,
                        priority=item.priority,
                        payload=item.payload,
                        max_retries=item.max_retries,
                        run_at=run_at,
                        parent_job_id=item.parent_job_id,
                        tags=item.tags,
                        created_at=now_utc,
                        updated_at=now_utc,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["queue_id", "idempotency_key"],
                        index_where=text("idempotency_key IS NOT NULL"),
                    )
                    .returning(Job.id)
                )
                res_insert = await db.execute(insert_stmt)
                row = res_insert.fetchone()
                if row:
                    resolved_job_ids.append(row[0])
                else:
                    stmt = select(Job.id).where(
                        Job.queue_id == target_queue_id,
                        Job.idempotency_key == item.idempotency_key,
                    )
                    res = await db.execute(stmt)
                    existing_id = res.scalar_one()
                    resolved_job_ids.append(existing_id)
            else:
                job = Job(
                    queue_id=target_queue_id,
                    idempotency_key=None,
                    name=item.name,
                    status=initial_status,
                    priority=item.priority,
                    payload=item.payload,
                    max_retries=item.max_retries,
                    run_at=run_at,
                    parent_job_id=item.parent_job_id,
                    tags=item.tags,
                )
                db.add(job)
                await db.flush()
                resolved_job_ids.append(job.id)

        await db.commit()

        # Query all resolved jobs in batch
        stmt = select(Job).where(Job.id.in_(resolved_job_ids))
        res = await db.execute(stmt)
        jobs_map = {j.id: j for j in res.scalars().all()}

        return [JobResponse.model_validate(jobs_map[jid]) for jid in resolved_job_ids if jid in jobs_map]

    @staticmethod
    async def list_jobs(
        db: AsyncSession,
        user: User,
        project_id: Optional[uuid.UUID] = None,
        queue_id: Optional[uuid.UUID] = None,
        status_filter: Optional[JobStatus] = None,
        tag: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> JobListResponse:
        # Base query joined with Project to enforce org tenancy
        query = select(Job).join(Queue, Job.queue_id == Queue.id).join(Project, Queue.project_id == Project.id).where(Project.org_id == user.org_id)

        if project_id:
            query = query.where(Project.id == project_id)
        if queue_id:
            query = query.where(Queue.id == queue_id)
        if status_filter:
            query = query.where(Job.status == status_filter)
        if tag:
            query = query.where(Job.tags.contains([tag]))
        if search:
            query = query.where(
                or_(
                    Job.name.ilike(f"%{search}%"),
                    Job.idempotency_key.ilike(f"%{search}%"),
                )
            )

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Pagination & Ordering
        offset = (page - 1) * page_size
        query = query.order_by(desc(Job.created_at)).offset(offset).limit(page_size)

        result = await db.execute(query)
        jobs = result.scalars().all()

        total_pages = math.ceil(total / page_size) if total > 0 else 1

        return JobListResponse(
            items=[JobResponse.model_validate(j) for j in jobs],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    @staticmethod
    async def get_job(db: AsyncSession, user: User, job_id: uuid.UUID) -> JobDetailResponse:
        stmt = (
            select(Job)
            .join(Queue, Job.queue_id == Queue.id)
            .join(Project, Queue.project_id == Project.id)
            .options(
                selectinload(Job.executions),
                selectinload(Job.dlq_entry),
            )
            .where(Job.id == job_id, Project.org_id == user.org_id)
        )
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found or access denied",
            )

        resp = JobDetailResponse.model_validate(job)

        # ⏱️ Calculate Job Latency & Observability Metrics
        if job.started_at and job.created_at:
            resp.queue_wait_ms = max(0, int((job.started_at - job.created_at).total_seconds() * 1000))
        elif job.executions:
            first_exec = min(job.executions, key=lambda e: e.started_at)
            resp.queue_wait_ms = max(0, int((first_exec.started_at - job.created_at).total_seconds() * 1000))

        if job.executions:
            resp.total_execution_time_ms = sum(e.duration_ms for e in job.executions)
            latest_exec = max(job.executions, key=lambda e: e.attempt_number)
            resp.execution_duration_ms = latest_exec.duration_ms
        elif job.completed_at and job.started_at:
            resp.execution_duration_ms = max(0, int((job.completed_at - job.started_at).total_seconds() * 1000))
            resp.total_execution_time_ms = resp.execution_duration_ms

        resp.retry_count = max(0, job.attempt_count - 1)
        return resp

    @staticmethod
    async def cancel_job(db: AsyncSession, user: User, job_id: uuid.UUID) -> JobResponse:
        stmt = (
            select(Job)
            .join(Queue, Job.queue_id == Queue.id)
            .join(Project, Queue.project_id == Project.id)
            .where(Job.id == job_id, Project.org_id == user.org_id)
        )
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found or access denied",
            )

        if job.status in (JobStatus.COMPLETED, JobStatus.CANCELLED):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel job in '{job.status.value}' state",
            )

        job.status = JobStatus.CANCELLED
        job.locked_by_worker_id = None
        job.lock_expires_at = None
        job.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(job)

        return JobResponse.model_validate(job)

    @staticmethod
    async def retry_job(db: AsyncSession, user: User, job_id: uuid.UUID) -> JobResponse:
        """Force manual re-enqueuing of a failed, cancelled, or DLQ job."""
        stmt = (
            select(Job)
            .join(Queue, Job.queue_id == Queue.id)
            .join(Project, Queue.project_id == Project.id)
            .where(Job.id == job_id, Project.org_id == user.org_id)
        )
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found or access denied",
            )

        now_utc = datetime.now(timezone.utc)
        job.status = JobStatus.QUEUED
        job.run_at = now_utc
        job.locked_by_worker_id = None
        job.lock_expires_at = None
        job.error_message = None
        job.updated_at = now_utc
        await db.commit()
        await db.refresh(job)

        return JobResponse.model_validate(job)

    @staticmethod
    async def get_job_logs(db: AsyncSession, user: User, job_id: uuid.UUID) -> List[JobExecutionResponse]:
        detail = await JobService.get_job(db, user, job_id)
        return detail.executions
