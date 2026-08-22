import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from backend.app.models import ScheduledJob, Queue, Project, User
from backend.app.schemas.schedule import (
    ScheduledJobCreate,
    ScheduledJobUpdate,
    ScheduledJobResponse,
)
from backend.app.services.queue_service import QueueService
from worker.app.cron import CronDispatcher


class ScheduleService:
    @staticmethod
    async def create_schedule(
        db: AsyncSession,
        user: User,
        queue_id: uuid.UUID,
        req: ScheduledJobCreate,
    ) -> ScheduledJobResponse:
        queue = await QueueService.get_queue(db, user, queue_id)

        now_utc = datetime.now(timezone.utc)
        next_run = CronDispatcher.compute_next_run(req.cron_expression, now_utc)

        schedule = ScheduledJob(
            project_id=queue.project_id,
            queue_id=queue.id,
            name=req.name,
            cron_expression=req.cron_expression,
            payload=req.payload,
            priority=req.priority,
            is_active=True,
            next_run_at=next_run,
            timezone=req.timezone,
        )
        db.add(schedule)
        await db.commit()
        await db.refresh(schedule)

        return ScheduledJobResponse.model_validate(schedule)

    @staticmethod
    async def list_schedules(
        db: AsyncSession,
        user: User,
        project_id: Optional[uuid.UUID] = None,
        queue_id: Optional[uuid.UUID] = None,
    ) -> List[ScheduledJobResponse]:
        query = (
            select(ScheduledJob)
            .join(Queue, ScheduledJob.queue_id == Queue.id)
            .join(Project, Queue.project_id == Project.id)
            .where(Project.org_id == user.org_id)
        )

        if project_id:
            query = query.where(Project.id == project_id)
        if queue_id:
            query = query.where(Queue.id == queue_id)

        result = await db.execute(query.order_by(ScheduledJob.created_at.desc()))
        schedules = result.scalars().all()
        return [ScheduledJobResponse.model_validate(s) for s in schedules]

    @staticmethod
    async def get_schedule(
        db: AsyncSession,
        user: User,
        schedule_id: uuid.UUID,
    ) -> ScheduledJobResponse:
        stmt = (
            select(ScheduledJob)
            .join(Queue, ScheduledJob.queue_id == Queue.id)
            .join(Project, Queue.project_id == Project.id)
            .where(ScheduledJob.id == schedule_id, Project.org_id == user.org_id)
        )
        res = await db.execute(stmt)
        schedule = res.scalar_one_or_none()
        if not schedule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Schedule not found or access denied",
            )
        return ScheduledJobResponse.model_validate(schedule)

    @staticmethod
    async def update_schedule(
        db: AsyncSession,
        user: User,
        schedule_id: uuid.UUID,
        req: ScheduledJobUpdate,
    ) -> ScheduledJobResponse:
        stmt = (
            select(ScheduledJob)
            .join(Queue, ScheduledJob.queue_id == Queue.id)
            .join(Project, Queue.project_id == Project.id)
            .where(ScheduledJob.id == schedule_id, Project.org_id == user.org_id)
        )
        res = await db.execute(stmt)
        schedule = res.scalar_one_or_none()
        if not schedule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Schedule not found or access denied",
            )

        update_data = req.model_dump(exclude_unset=True)
        if "cron_expression" in update_data and update_data["cron_expression"]:
            now_utc = datetime.now(timezone.utc)
            schedule.next_run_at = CronDispatcher.compute_next_run(update_data["cron_expression"], now_utc)

        for key, val in update_data.items():
            setattr(schedule, key, val)

        schedule.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(schedule)

        return ScheduledJobResponse.model_validate(schedule)

    @staticmethod
    async def pause_schedule(db: AsyncSession, user: User, schedule_id: uuid.UUID) -> ScheduledJobResponse:
        return await ScheduleService.update_schedule(
            db, user, schedule_id, ScheduledJobUpdate(is_active=False)
        )

    @staticmethod
    async def resume_schedule(db: AsyncSession, user: User, schedule_id: uuid.UUID) -> ScheduledJobResponse:
        return await ScheduleService.update_schedule(
            db, user, schedule_id, ScheduledJobUpdate(is_active=True)
        )

    @staticmethod
    async def delete_schedule(db: AsyncSession, user: User, schedule_id: uuid.UUID) -> dict:
        stmt = (
            select(ScheduledJob)
            .join(Queue, ScheduledJob.queue_id == Queue.id)
            .join(Project, Queue.project_id == Project.id)
            .where(ScheduledJob.id == schedule_id, Project.org_id == user.org_id)
        )
        res = await db.execute(stmt)
        schedule = res.scalar_one_or_none()
        if not schedule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Schedule not found or access denied",
            )

        await db.delete(schedule)
        await db.commit()
        return {"message": "Recurring schedule deleted", "schedule_id": str(schedule_id)}
