import os
import sys
import uuid
import socket
import asyncio
import logging
from typing import List, Optional, Set
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import AsyncSessionLocal
from backend.app.core.config import settings
from backend.app.models import Worker, WorkerStatus, Job
from worker.app.engine.claimer import AtomicClaimer
from worker.app.engine.runner import TaskRunner
from worker.app.heartbeat import WorkerHeartbeatEmitter

logger = logging.getLogger("scheduler.worker.daemon")


class WorkerDaemon:
    def __init__(
        self,
        worker_id: Optional[str] = None,
        concurrency: int = 5,
        assigned_queues: Optional[List[str]] = None,
        poll_interval: float = 0.2,
    ):
        self.worker_id = worker_id or f"worker-{socket.gethostname()[:12]}-{uuid.uuid4().hex[:6]}"
        self.hostname = socket.gethostname()
        self.pid = os.getpid()
        self.concurrency = concurrency
        self.assigned_queues = assigned_queues or []
        self.poll_interval = poll_interval
        self.semaphore = asyncio.Semaphore(concurrency)
        self.is_running = False
        self._active_tasks = set()
        self.active_job_ids: Set[uuid.UUID] = set()
        self.heartbeat_emitter = WorkerHeartbeatEmitter(self.worker_id, self.active_job_ids)

    async def register(self):
        """Register or update worker metadata in database on startup."""
        async with AsyncSessionLocal() as session:
            stmt = select(Worker).where(Worker.worker_id == self.worker_id)
            result = await session.execute(stmt)
            worker = result.scalar_one_or_none()

            now_utc = datetime.now(timezone.utc)
            if not worker:
                worker = Worker(
                    worker_id=self.worker_id,
                    hostname=self.hostname,
                    pid=self.pid,
                    concurrency_limit=self.concurrency,
                    current_active_jobs=0,
                    status=WorkerStatus.ALIVE,
                    assigned_queues=self.assigned_queues,
                    started_at=now_utc,
                    last_heartbeat_at=now_utc,
                )
                session.add(worker)
            else:
                worker.hostname = self.hostname
                worker.pid = self.pid
                worker.concurrency_limit = self.concurrency
                worker.status = WorkerStatus.ALIVE
                worker.assigned_queues = self.assigned_queues
                worker.last_heartbeat_at = now_utc

            await session.commit()
            logger.info(f"🚀 Worker '{self.worker_id}' registered successfully (Concurrency: {self.concurrency})")

    async def run_once(self, session: Optional[AsyncSession] = None) -> bool:
        """
        Poll and execute a single available job. Useful for tests and single-pass drains.
        Returns True if a job was found and executed, False if queue was empty.
        """
        if session:
            job = await AtomicClaimer.claim_next_job(
                session,
                self.worker_id,
                self.assigned_queues,
                lock_timeout_seconds=settings.JOB_LOCK_TIMEOUT_SECONDS,
            )
            if job:
                self.active_job_ids.add(job.id)
                try:
                    await TaskRunner.execute_job(session, job, self.worker_id)
                finally:
                    self.active_job_ids.discard(job.id)
                return True
            return False
        else:
            async with AsyncSessionLocal() as sess:
                job = await AtomicClaimer.claim_next_job(
                    sess,
                    self.worker_id,
                    self.assigned_queues,
                    lock_timeout_seconds=settings.JOB_LOCK_TIMEOUT_SECONDS,
                )
                if job:
                    self.active_job_ids.add(job.id)
                    try:
                        await TaskRunner.execute_job(sess, job, self.worker_id)
                    finally:
                        self.active_job_ids.discard(job.id)
                    return True
                return False

    async def _execute_with_semaphore(self, job_id: uuid.UUID, lease_token: Optional[uuid.UUID] = None):
        """Execute task within semaphore concurrency boundary and track active IDs."""
        self.active_job_ids.add(job_id)
        try:
            async with AsyncSessionLocal() as session:
                job = await session.get(Job, job_id)
                if job:
                    await TaskRunner.execute_job(session, job, self.worker_id, lease_token=lease_token)
        except Exception as e:
            logger.error(f"Error in task execution wrapper: {e}")
        finally:
            self.active_job_ids.discard(job_id)
            self.semaphore.release()

    async def start(self):
        """Main worker polling loop with active heartbeats."""
        await self.register()
        await self.heartbeat_emitter.start()
        self.is_running = True
        logger.info(f"⚡ Worker '{self.worker_id}' polling queues for ready jobs...")

        while self.is_running:
            await self.semaphore.acquire()
            if not self.is_running:
                self.semaphore.release()
                break

            try:
                async with AsyncSessionLocal() as session:
                    job = await AtomicClaimer.claim_next_job(
                        session,
                        self.worker_id,
                        self.assigned_queues,
                        lock_timeout_seconds=settings.JOB_LOCK_TIMEOUT_SECONDS,
                    )

                if job:
                    task = asyncio.create_task(self._execute_with_semaphore(job.id, job.lease_token))
                    self._active_tasks.add(task)
                    task.add_done_callback(self._active_tasks.discard)
                else:
                    self.semaphore.release()
                    await asyncio.sleep(self.poll_interval)

            except asyncio.CancelledError:
                self.semaphore.release()
                break
            except Exception as e:
                self.semaphore.release()
                logger.error(f"Error in worker polling loop: {e}")
                await asyncio.sleep(self.poll_interval)

    async def stop(self):
        """
        Graceful shutdown sequence:
        1. Stop accepting/polling new jobs (is_running = False)
        2. Transition status to DRAINING in database & emit draining heartbeat
        3. Finish active in-flight tasks (await _active_tasks)
        4. Stop heartbeat emitter
        5. Mark worker status = DEAD on exit
        """
        logger.info(f"🛑 Worker '{self.worker_id}' received shutdown signal (SIGTERM/SIGINT). Transitioning to DRAINING...")
        self.is_running = False

        # 1. Update database status to DRAINING
        async with AsyncSessionLocal() as session:
            stmt = (
                select(Worker)
                .where(Worker.worker_id == self.worker_id)
            )
            res = await session.execute(stmt)
            worker = res.scalar_one_or_none()
            if worker:
                worker.status = WorkerStatus.DRAINING
                await session.commit()

        # 2. Emit draining heartbeat
        try:
            await self.heartbeat_emitter.emit_once()
        except Exception as e:
            logger.warning(f"Could not emit draining heartbeat: {e}")

        # 3. Wait for in-flight tasks to finish completely
        if self._active_tasks:
            logger.info(f"⏳ Draining {len(self._active_tasks)} in-flight tasks to completion...")
            await asyncio.gather(*self._active_tasks, return_exceptions=True)

        # 4. Stop heartbeat emitter
        await self.heartbeat_emitter.stop()

        # 5. Mark worker status as DEAD on final exit
        async with AsyncSessionLocal() as session:
            stmt = select(Worker).where(Worker.worker_id == self.worker_id)
            res = await session.execute(stmt)
            worker = res.scalar_one_or_none()
            if worker:
                worker.status = WorkerStatus.DEAD
                worker.current_active_jobs = 0
                await session.commit()

        logger.info(f"👋 Worker '{self.worker_id}' graceful shutdown complete.")
