import uuid
import math
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import select, func, desc, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from backend.app.models import DLQEntry, Job, Queue, Project, User, JobStatus
from backend.app.schemas.dlq import (
    DLQEntryDetailResponse,
    DLQListResponse,
    DLQReplayResponse,
)


class DLQService:
    @staticmethod
    async def list_dlq_entries(
        db: AsyncSession,
        user: User,
        queue_id: Optional[uuid.UUID] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> DLQListResponse:
        query = (
            select(DLQEntry)
            .join(Queue, DLQEntry.queue_id == Queue.id)
            .join(Project, Queue.project_id == Project.id)
            .where(Project.org_id == user.org_id)
            .options(selectinload(DLQEntry.job))
        )

        if queue_id:
            query = query.where(DLQEntry.queue_id == queue_id)

        count_query = select(func.count()).select_from(query.subquery())
        total_res = await db.execute(count_query)
        total = total_res.scalar() or 0

        offset = (page - 1) * page_size
        query = query.order_by(desc(DLQEntry.moved_to_dlq_at)).offset(offset).limit(page_size)
        result = await db.execute(query)
        entries = result.scalars().all()

        total_pages = math.ceil(total / page_size) if total > 0 else 1

        return DLQListResponse(
            items=[DLQEntryDetailResponse.model_validate(e) for e in entries],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    @staticmethod
    async def get_dlq_entry(
        db: AsyncSession,
        user: User,
        dlq_id: uuid.UUID,
    ) -> DLQEntryDetailResponse:
        stmt = (
            select(DLQEntry)
            .join(Queue, DLQEntry.queue_id == Queue.id)
            .join(Project, Queue.project_id == Project.id)
            .where(DLQEntry.id == dlq_id, Project.org_id == user.org_id)
            .options(selectinload(DLQEntry.job))
        )
        res = await db.execute(stmt)
        entry = res.scalar_one_or_none()
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="DLQ entry not found or access denied",
            )
        return DLQEntryDetailResponse.model_validate(entry)

    @staticmethod
    async def replay_dlq_entry(
        db: AsyncSession,
        user: User,
        dlq_id: uuid.UUID,
    ) -> DLQReplayResponse:
        stmt = (
            select(DLQEntry)
            .join(Queue, DLQEntry.queue_id == Queue.id)
            .join(Project, Queue.project_id == Project.id)
            .where(DLQEntry.id == dlq_id, Project.org_id == user.org_id)
            .options(selectinload(DLQEntry.job))
        )
        res = await db.execute(stmt)
        entry = res.scalar_one_or_none()
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="DLQ entry not found or access denied",
            )

        now_utc = datetime.now(timezone.utc)
        entry.is_replayed = True
        entry.replayed_at = now_utc

        # Reset Job to queued state with fresh schedule
        if entry.job:
            entry.job.status = JobStatus.QUEUED
            entry.job.run_at = now_utc
            entry.job.locked_by_worker_id = None
            entry.job.lock_expires_at = None
            entry.job.error_message = None
            entry.job.updated_at = now_utc

        await db.commit()

        return DLQReplayResponse(
            message="DLQ job successfully replayed back to queue",
            replayed_count=1,
            job_ids=[entry.job_id],
        )

    @staticmethod
    async def replay_all_dlq_entries(
        db: AsyncSession,
        user: User,
        queue_id: uuid.UUID,
    ) -> DLQReplayResponse:
        stmt = (
            select(DLQEntry)
            .join(Queue, DLQEntry.queue_id == Queue.id)
            .join(Project, Queue.project_id == Project.id)
            .where(
                DLQEntry.queue_id == queue_id,
                DLQEntry.is_replayed == False,
                Project.org_id == user.org_id,
            )
            .options(selectinload(DLQEntry.job))
        )
        res = await db.execute(stmt)
        entries = res.scalars().all()

        if not entries:
            return DLQReplayResponse(
                message="No pending DLQ entries to replay in this queue",
                replayed_count=0,
                job_ids=[],
            )

        now_utc = datetime.now(timezone.utc)
        replayed_ids = []

        for entry in entries:
            entry.is_replayed = True
            entry.replayed_at = now_utc
            if entry.job:
                entry.job.status = JobStatus.QUEUED
                entry.job.run_at = now_utc
                entry.job.locked_by_worker_id = None
                entry.job.lock_expires_at = None
                entry.job.error_message = None
                entry.job.updated_at = now_utc
                replayed_ids.append(entry.job_id)

        await db.commit()

        return DLQReplayResponse(
            message=f"Successfully replayed {len(replayed_ids)} DLQ jobs back to queue",
            replayed_count=len(replayed_ids),
            job_ids=replayed_ids,
        )

    @staticmethod
    async def purge_dlq_entry(
        db: AsyncSession,
        user: User,
        dlq_id: uuid.UUID,
    ) -> dict:
        stmt = (
            select(DLQEntry)
            .join(Queue, DLQEntry.queue_id == Queue.id)
            .join(Project, Queue.project_id == Project.id)
            .where(DLQEntry.id == dlq_id, Project.org_id == user.org_id)
        )
        res = await db.execute(stmt)
        entry = res.scalar_one_or_none()
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="DLQ entry not found or access denied",
            )

        await db.delete(entry)
        await db.commit()
        return {"message": "DLQ entry permanently purged", "dlq_id": str(dlq_id)}
