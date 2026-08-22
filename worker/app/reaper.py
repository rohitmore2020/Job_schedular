import asyncio
import logging
from typing import Dict, Any, List
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import AsyncSessionLocal
from backend.app.core.config import settings
from backend.app.models import Job, DLQEntry, Worker, JobStatus, WorkerStatus

logger = logging.getLogger("scheduler.reaper")


class LeaseReaper:
    """
    Background Janitor Daemon that identifies crashed / zombie workers and
    reclaims jobs whose execution leases expired (`lock_expires_at < NOW()`).
    """

    def __init__(self, scan_interval: int = 10):
        self.scan_interval = scan_interval
        self.is_running = False
        self._task: asyncio.Task = None

    async def reap_expired_leases(self, session: AsyncSession) -> Dict[str, Any]:
        """
        Executes one sweep of expired lease recovery.
        """
        now_utc = datetime.now(timezone.utc)

        # 1. Detect dead workers (no heartbeat for > 30 seconds)
        dead_worker_threshold = now_utc - timedelta(seconds=settings.JOB_LOCK_TIMEOUT_SECONDS)
        mark_dead_stmt = (
            update(Worker)
            .where(
                Worker.status == WorkerStatus.ALIVE,
                Worker.last_heartbeat_at < dead_worker_threshold,
            )
            .values(status=WorkerStatus.DEAD)
            .returning(Worker.worker_id)
        )
        dead_workers_res = await session.execute(mark_dead_stmt)
        dead_worker_ids = [row[0] for row in dead_workers_res.fetchall()]

        if dead_worker_ids:
            logger.warning(f"💀 [Reaper] Detected {len(dead_worker_ids)} dead worker(s): {dead_worker_ids}")

        # 2. Find jobs with expired leases
        stmt = (
            select(Job)
            .where(
                Job.status == JobStatus.RUNNING,
                Job.lock_expires_at < now_utc,
            )
        )
        result = await session.execute(stmt)
        expired_jobs = result.scalars().all()

        requeued_count = 0
        dlq_count = 0

        for job in expired_jobs:
            logger.warning(
                f"⚠️ [Reaper] Found expired lease for Job '{job.name}' (ID: {job.id}, Worker: {job.locked_by_worker_id}, Attempts: {job.attempt_count}/{job.max_retries})"
            )

            if job.attempt_count < job.max_retries:
                # Re-queue job for healthy workers (resetting lease fencing token)
                job.status = JobStatus.QUEUED
                job.run_at = now_utc
                job.locked_by_worker_id = None
                job.lease_token = None
                job.lock_expires_at = None
                job.error_message = "Worker lease expired (Worker crashed or lost heartbeat)"
                job.updated_at = now_utc
                requeued_count += 1
                logger.info(f"🔄 [Reaper] Re-queued Job '{job.name}' ({job.id}) for reprocessing")
            else:
                # Retries exhausted -> Escalated to Dead Letter Queue
                job.status = JobStatus.DEAD_LETTER
                job.locked_by_worker_id = None
                job.lease_token = None
                job.lock_expires_at = None
                job.error_message = "Worker lease expired and maximum retries exhausted"
                job.updated_at = now_utc
                dlq_count += 1

                dlq = DLQEntry(
                    job_id=job.id,
                    queue_id=job.queue_id,
                    failed_reason=f"Worker lease expired after {job.attempt_count} attempts",
                    total_attempts=job.attempt_count,
                    last_error="Worker failed to send heartbeat / lease expired",
                    moved_to_dlq_at=now_utc,
                )
                session.add(dlq)
                logger.warning(f"💀 [Reaper] Escalated Job '{job.name}' ({job.id}) to Dead Letter Queue")

        await session.commit()

        return {
            "dead_workers_detected": len(dead_worker_ids),
            "jobs_requeued": requeued_count,
            "jobs_moved_to_dlq": dlq_count,
            "total_expired_jobs": len(expired_jobs),
        }

    async def start(self):
        self.is_running = True
        self._task = asyncio.create_task(self._reaper_loop())
        logger.info(f"🧹 Lease Reaper daemon started (scanning every {self.scan_interval}s)")

    async def stop(self):
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Lease Reaper daemon stopped")

    async def _reaper_loop(self):
        while self.is_running:
            try:
                async with AsyncSessionLocal() as session:
                    await self.reap_expired_leases(session)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in reaper loop: {e}")

            await asyncio.sleep(self.scan_interval)
