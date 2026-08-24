import asyncio
import uuid
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import AsyncSessionLocal
from backend.app.models import Job, JobStatus
from backend.app.core.ws_manager import ws_manager

logger = logging.getLogger("scheduler.promoter")


class ScheduledJobPromoter:
    """
    Background daemon that promotes delayed/scheduled jobs (`status = 'scheduled'`)
    to `status = 'queued'` when their scheduled fire time is reached (`run_at <= NOW()`).
    Uses PostgreSQL `FOR UPDATE SKIP LOCKED` for strict race-safe mutual exclusion
    across multiple promoter replicas.
    """

    def __init__(self, scan_interval_seconds: float = 1.0, batch_size: int = 100):
        self.scan_interval_seconds = scan_interval_seconds
        self.batch_size = batch_size
        self.is_running = False
        self._task: Optional[asyncio.Task] = None

    async def promote_due_jobs(self, session: AsyncSession, queue_id: Optional[uuid.UUID] = None) -> int:
        """
        Atomically promotes all due scheduled jobs whose `run_at <= NOW()`.
        Ensures DAG child jobs are only promoted if their parent is completed.
        Returns count of promoted jobs.
        """
        where_extra = "AND j.queue_id = :queue_id" if queue_id else ""
        params = {"batch_size": self.batch_size}
        if queue_id:
            params["queue_id"] = queue_id

        stmt = text(f"""
            WITH due_jobs AS (
                SELECT j.id
                FROM jobs j
                WHERE j.status = 'scheduled'
                  AND j.run_at <= NOW()
                  {where_extra}
                  AND (
                      j.parent_job_id IS NULL
                      OR EXISTS (
                          SELECT 1 FROM jobs pj
                          WHERE pj.id = j.parent_job_id
                            AND pj.status = 'completed'
                      )
                  )
                ORDER BY j.priority DESC, j.run_at ASC
                LIMIT :batch_size
                FOR UPDATE SKIP LOCKED
            )
            UPDATE jobs
            SET status = 'queued',
                updated_at = NOW()
            FROM due_jobs
            WHERE jobs.id = due_jobs.id
            RETURNING jobs.id;
        """)

        res = await session.execute(stmt, params)
        promoted_ids = [r[0] for r in res.fetchall()]
        await session.commit()

        if promoted_ids:
            logger.info(f"⚡ [Promoter] Promoted {len(promoted_ids)} scheduled jobs to 'queued' state")
            await ws_manager.broadcast("jobs_promoted", {
                "count": len(promoted_ids),
                "job_ids": [str(x) for x in promoted_ids],
            })

        return len(promoted_ids)

    async def start(self):
        self.is_running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"⏳ Scheduled Job Promoter daemon started (scanning every {self.scan_interval_seconds}s)")

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Scheduled Job Promoter daemon stopped")

    async def _loop(self):
        while self.is_running:
            try:
                async with AsyncSessionLocal() as session:
                    await self.promote_due_jobs(session)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in promoter loop: {e}", exc_info=True)
            await asyncio.sleep(self.scan_interval_seconds)
