import os
import psutil
import asyncio
import logging
from typing import Set, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import AsyncSessionLocal
from backend.app.core.config import settings
from backend.app.models import Worker, WorkerHeartbeat, Job, JobStatus
from backend.app.core.ws_manager import ws_manager

logger = logging.getLogger("scheduler.worker.heartbeat")


class WorkerHeartbeatEmitter:
    """
    Periodically sends worker CPU/RAM telemetry to `worker_heartbeats`
    and extends `lock_expires_at` for all active in-flight jobs.
    """

    def __init__(self, worker_id: str, active_job_ids_ref: Set[str]):
        self.worker_id = worker_id
        self.active_job_ids = active_job_ids_ref
        self.is_running = False
        self._task: asyncio.Task = None
        self._process = psutil.Process(os.getpid())

    async def start(self):
        self.is_running = True
        self._task = asyncio.create_task(self._heartbeat_loop())
        logger.info(f"💓 Heartbeat emitter started for worker '{self.worker_id}' (every {settings.HEARTBEAT_INTERVAL_SECONDS}s)")

    async def stop(self):
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"🛑 Heartbeat emitter stopped for worker '{self.worker_id}'")

    async def emit_once(self, session: Optional[AsyncSession] = None) -> dict:
        """Collect metrics, extend leases, and write to database."""
        now_utc = datetime.now(timezone.utc)
        cpu_percent = self._process.cpu_percent(interval=None)
        memory_mb = self._process.memory_info().rss / (1024 * 1024)
        active_count = len(self.active_job_ids)

        if session:
            await self._record_heartbeat(session, now_utc, cpu_percent, memory_mb, active_count)
        else:
            async with AsyncSessionLocal() as sess:
                await self._record_heartbeat(sess, now_utc, cpu_percent, memory_mb, active_count)

        data = {
            "worker_id": self.worker_id,
            "cpu_percent": cpu_percent,
            "memory_mb": round(memory_mb, 2),
            "active_jobs": active_count,
            "timestamp": now_utc.isoformat(),
        }

        await ws_manager.broadcast("worker_heartbeat", data)

        return data

    async def _record_heartbeat(
        self, session: AsyncSession, now_utc: datetime, cpu_percent: float, memory_mb: float, active_count: int
    ):
        # 1. Update Worker liveness & active job count
        stmt = (
            update(Worker)
            .where(Worker.worker_id == self.worker_id)
            .values(
                last_heartbeat_at=now_utc,
                current_active_jobs=active_count,
            )
        )
        await session.execute(stmt)

        # 2. Record telemetry point
        hb = WorkerHeartbeat(
            worker_id=self.worker_id,
            cpu_percent=cpu_percent,
            memory_mb=memory_mb,
            active_jobs=active_count,
            timestamp=now_utc,
        )
        session.add(hb)

        # 3. Renew lease locks for in-flight jobs
        if self.active_job_ids:
            job_ids_list = list(self.active_job_ids)
            lease_extension = now_utc + timedelta(seconds=settings.JOB_LOCK_TIMEOUT_SECONDS)
            renew_stmt = (
                update(Job)
                .where(
                    Job.id.in_(job_ids_list),
                    Job.locked_by_worker_id == self.worker_id,
                    Job.status == JobStatus.RUNNING,
                )
                .values(lock_expires_at=lease_extension)
            )
            await session.execute(renew_stmt)

        await session.commit()

    async def _heartbeat_loop(self):
        while self.is_running:
            try:
                await self.emit_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")

            await asyncio.sleep(settings.HEARTBEAT_INTERVAL_SECONDS)
