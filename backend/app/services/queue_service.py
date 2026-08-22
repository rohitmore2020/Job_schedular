import uuid
from typing import List, Optional
from sqlalchemy import select, func, case
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from backend.app.models import Queue, RetryPolicy, Project, Job, User, JobStatus
from backend.app.schemas.queue import (
    QueueCreate,
    QueueUpdate,
    QueueResponse,
    QueueStats,
    RetryPolicyResponse,
)
from backend.app.services.project_service import ProjectService


class QueueService:
    @staticmethod
    async def get_queue_stats(db: AsyncSession, queue_id: uuid.UUID) -> QueueStats:
        """Compute live job counts by status for a queue."""
        stmt = select(
            func.count(case((Job.status == JobStatus.QUEUED, 1))).label("queued"),
            func.count(case((Job.status == JobStatus.RUNNING, 1))).label("running"),
            func.count(case((Job.status == JobStatus.COMPLETED, 1))).label("completed"),
            func.count(case((Job.status == JobStatus.FAILED, 1))).label("failed"),
            func.count(case((Job.status == JobStatus.DEAD_LETTER, 1))).label("dead_letter"),
            func.count(Job.id).label("total"),
        ).where(Job.queue_id == queue_id)

        result = await db.execute(stmt)
        row = result.fetchone()
        if row:
            return QueueStats(
                queued=row[0] or 0,
                running=row[1] or 0,
                completed=row[2] or 0,
                failed=row[3] or 0,
                dead_letter=row[4] or 0,
                total=row[5] or 0,
            )
        return QueueStats()

    @staticmethod
    async def list_queues(
        db: AsyncSession, user: User, project_id: uuid.UUID
    ) -> List[QueueResponse]:
        project = await ProjectService.get_project(db, user, project_id)

        stmt = (
            select(Queue)
            .options(selectinload(Queue.retry_policy))
            .where(Queue.project_id == project.id)
            .order_by(Queue.priority.desc(), Queue.name.asc())
        )
        result = await db.execute(stmt)
        queues = result.scalars().all()

        responses = []
        for q in queues:
            stats = await QueueService.get_queue_stats(db, q.id)
            resp = QueueResponse.model_validate(q)
            resp.stats = stats
            responses.append(resp)
        return responses

    @staticmethod
    async def get_queue(db: AsyncSession, user: User, queue_id: uuid.UUID) -> Queue:
        stmt = (
            select(Queue)
            .join(Project, Queue.project_id == Project.id)
            .options(selectinload(Queue.retry_policy))
            .where(Queue.id == queue_id, Project.org_id == user.org_id)
        )
        result = await db.execute(stmt)
        queue = result.scalar_one_or_none()
        if not queue:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Queue not found or access denied",
            )
        return queue

    @staticmethod
    async def create_queue(
        db: AsyncSession, user: User, project_id: uuid.UUID, req: QueueCreate
    ) -> QueueResponse:
        project = await ProjectService.get_project(db, user, project_id)

        # Check for unique name in project
        existing = await db.execute(
            select(Queue).where(
                Queue.project_id == project.id, Queue.name == req.name
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Queue with name '{req.name}' already exists in this project",
            )

        queue = Queue(
            project_id=project.id,
            name=req.name,
            priority=req.priority,
            concurrency_limit=req.concurrency_limit,
            rate_limit_rps=req.rate_limit_rps,
            is_paused=False,
        )
        db.add(queue)
        await db.flush()

        # Add Retry Policy
        retry_policy_data = req.retry_policy
        if retry_policy_data:
            policy = RetryPolicy(
                queue_id=queue.id,
                strategy=retry_policy_data.strategy,
                max_retries=retry_policy_data.max_retries,
                initial_interval_sec=retry_policy_data.initial_interval_sec,
                max_interval_sec=retry_policy_data.max_interval_sec,
                backoff_multiplier=retry_policy_data.backoff_multiplier,
                jitter=retry_policy_data.jitter,
            )
            db.add(policy)
        else:
            # Default Exponential Retry Policy
            policy = RetryPolicy(queue_id=queue.id)
            db.add(policy)

        await db.commit()
        await db.refresh(queue)
        
        # Load with retry policy
        refreshed_q = await QueueService.get_queue(db, user, queue.id)
        resp = QueueResponse.model_validate(refreshed_q)
        resp.stats = QueueStats()
        return resp

    @staticmethod
    async def update_queue(
        db: AsyncSession, user: User, queue_id: uuid.UUID, req: QueueUpdate
    ) -> QueueResponse:
        queue = await QueueService.get_queue(db, user, queue_id)

        if req.priority is not None:
            queue.priority = req.priority
        if req.concurrency_limit is not None:
            queue.concurrency_limit = req.concurrency_limit
        if req.rate_limit_rps is not None:
            queue.rate_limit_rps = req.rate_limit_rps

        if req.retry_policy:
            if queue.retry_policy:
                rp = queue.retry_policy
                if req.retry_policy.strategy is not None:
                    rp.strategy = req.retry_policy.strategy
                if req.retry_policy.max_retries is not None:
                    rp.max_retries = req.retry_policy.max_retries
                if req.retry_policy.initial_interval_sec is not None:
                    rp.initial_interval_sec = req.retry_policy.initial_interval_sec
                if req.retry_policy.max_interval_sec is not None:
                    rp.max_interval_sec = req.retry_policy.max_interval_sec
                if req.retry_policy.backoff_multiplier is not None:
                    rp.backoff_multiplier = req.retry_policy.backoff_multiplier
                if req.retry_policy.jitter is not None:
                    rp.jitter = req.retry_policy.jitter
            else:
                new_policy = RetryPolicy(
                    queue_id=queue.id,
                    strategy=req.retry_policy.strategy or RetryStrategy.EXPONENTIAL,
                    max_retries=req.retry_policy.max_retries or 3,
                    initial_interval_sec=req.retry_policy.initial_interval_sec or 5,
                    max_interval_sec=req.retry_policy.max_interval_sec or 3600,
                    backoff_multiplier=req.retry_policy.backoff_multiplier or 2.0,
                    jitter=req.retry_policy.jitter if req.retry_policy.jitter is not None else True,
                )
                db.add(new_policy)

        await db.commit()
        await db.refresh(queue)
        refreshed_q = await QueueService.get_queue(db, user, queue.id)
        stats = await QueueService.get_queue_stats(db, queue.id)
        resp = QueueResponse.model_validate(refreshed_q)
        resp.stats = stats
        return resp

    @staticmethod
    async def pause_queue(db: AsyncSession, user: User, queue_id: uuid.UUID) -> QueueResponse:
        queue = await QueueService.get_queue(db, user, queue_id)
        queue.is_paused = True
        await db.commit()
        await db.refresh(queue)
        stats = await QueueService.get_queue_stats(db, queue.id)
        resp = QueueResponse.model_validate(queue)
        resp.stats = stats
        return resp

    @staticmethod
    async def resume_queue(db: AsyncSession, user: User, queue_id: uuid.UUID) -> QueueResponse:
        queue = await QueueService.get_queue(db, user, queue_id)
        queue.is_paused = False
        await db.commit()
        await db.refresh(queue)
        stats = await QueueService.get_queue_stats(db, queue.id)
        resp = QueueResponse.model_validate(queue)
        resp.stats = stats
        return resp

    @staticmethod
    async def delete_queue(db: AsyncSession, user: User, queue_id: uuid.UUID) -> dict:
        queue = await QueueService.get_queue(db, user, queue_id)
        await db.delete(queue)
        await db.commit()
        return {"success": True, "message": f"Queue '{queue.name}' deleted successfully"}
