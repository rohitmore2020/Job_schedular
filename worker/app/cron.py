import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from croniter import croniter
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import AsyncSessionLocal
from backend.app.models import ScheduledJob, Job, JobStatus

logger = logging.getLogger("scheduler.cron")


class CronDispatcher:
    """
    Background scheduler daemon that evaluates recurring cron schedules
    and spawns Job instances at their calculated fire times.
    """

    def __init__(self, check_interval_seconds: int = 5):
        self.check_interval_seconds = check_interval_seconds
        self.is_running = False
        self._task: Optional[asyncio.Task] = None

    @staticmethod
    def compute_next_run(cron_expr: str, base_time: Optional[datetime] = None) -> datetime:
        """Calculate the next execution timestamp from a standard cron expression in UTC."""
        base = base_time or datetime.now(timezone.utc)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        itr = croniter(cron_expr, base)
        next_dt = itr.get_next(datetime)
        if next_dt.tzinfo is None:
            next_dt = next_dt.replace(tzinfo=timezone.utc)
        return next_dt

    async def dispatch_due_schedules(
        self, session: AsyncSession, schedule_id: Optional[uuid.UUID] = None
    ) -> int:
        """
        Scan and enqueue jobs for all active schedules whose `next_run_at <= NOW()`.
        Uses a unique logical execution key `cron:<schedule_id>:<scheduled_for>`
        and PostgreSQL `ON CONFLICT DO NOTHING` to guarantee zero duplicate occurrences
        even across concurrent scheduler replicas.
        """
        now_utc = datetime.now(timezone.utc)

        # Lock due schedules to prevent double triggering across scheduler replicas
        stmt = (
            select(ScheduledJob)
            .where(
                ScheduledJob.is_active == True,
                ScheduledJob.next_run_at <= now_utc,
            )
            .with_for_update(skip_locked=True)
        )
        if schedule_id:
            stmt = stmt.where(ScheduledJob.id == schedule_id)

        result = await session.execute(stmt)
        due_schedules = result.scalars().all()

        if not due_schedules:
            return 0

        dispatched_count = 0
        for schedule in due_schedules:
            scheduled_for = schedule.next_run_at
            # Logical execution key format: 'cron:<schedule_id>:<scheduled_for_iso>'
            idempotency_key = f"cron:{schedule.id}:{scheduled_for.isoformat()}"

            # 1. Atomic INSERT with ON CONFLICT (queue_id, idempotency_key) DO NOTHING
            insert_stmt = (
                pg_insert(Job)
                .values(
                    id=uuid.uuid4(),
                    queue_id=schedule.queue_id,
                    idempotency_key=idempotency_key,
                    name=schedule.name,
                    status=JobStatus.QUEUED,
                    priority=schedule.priority,
                    payload=schedule.payload,
                    max_retries=3,
                    run_at=scheduled_for,
                    tags=["cron", f"schedule:{schedule.id}"],
                    created_at=now_utc,
                    updated_at=now_utc,
                )
                .on_conflict_do_nothing(
                    index_elements=["queue_id", "idempotency_key"],
                    index_where=text("idempotency_key IS NOT NULL"),
                )
                .returning(Job.id)
            )
            res_insert = await session.execute(insert_stmt)
            row = res_insert.fetchone()

            if row:
                dispatched_count += 1
                logger.info(
                    f"⏰ [Cron] Dispatched recurring Job '{schedule.name}' (Schedule: {schedule.id}, Key: {idempotency_key})"
                )
            else:
                logger.info(
                    f"🛡️ [Cron Guard] Duplicate occurrence suppressed for Schedule '{schedule.name}' (Key: {idempotency_key})"
                )

            # 2. Advance schedule next_run_at and increment run counter
            next_fire = self.compute_next_run(schedule.cron_expression, scheduled_for)
            schedule.last_run_at = scheduled_for
            schedule.next_run_at = next_fire
            schedule.total_runs_count = (schedule.total_runs_count or 0) + (1 if row else 0)
            schedule.updated_at = now_utc

        await session.commit()
        return dispatched_count

    async def start(self):
        self.is_running = True
        self._task = asyncio.create_task(self._cron_loop())
        logger.info(f"⏰ Cron Dispatcher started (evaluating every {self.check_interval_seconds}s)")

    async def stop(self):
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Cron Dispatcher stopped")

    async def _cron_loop(self):
        while self.is_running:
            try:
                async with AsyncSessionLocal() as session:
                    await self.dispatch_due_schedules(session)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cron dispatcher loop: {e}")

            await asyncio.sleep(self.check_interval_seconds)
