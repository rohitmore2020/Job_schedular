import uuid
from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models import Job, Queue, RetryPolicy
from worker.app.engine.rate_limiter import QueueRateLimiter


class AtomicClaimer:
    """
    Executes atomic queue polling using PostgreSQL's `FOR UPDATE SKIP LOCKED`.
    Guarantees strict zero-double-execution, respects queue priority, concurrency limits,
    pause flags, and token-bucket rate limits in a single ACID transaction.
    """

    @staticmethod
    async def claim_next_job(
        session: AsyncSession,
        worker_id: str,
        assigned_queues: Optional[List[str]] = None,
        queue_id: Optional[uuid.UUID] = None,
        lock_timeout_seconds: int = 30,
    ) -> Optional[Job]:
        """
        Atomically selects and claims the highest priority ready job.
        Enforces token-bucket rate limits per queue.
        """
        filter_clauses = []
        params = {
            "worker_id": worker_id,
            "lock_seconds": lock_timeout_seconds,
        }

        if queue_id:
            filter_clauses.append("AND q.id = :queue_id")
            params["queue_id"] = queue_id

        if assigned_queues and len(assigned_queues) > 0:
            filter_clauses.append("AND q.name = ANY(:assigned_queues)")
            params["assigned_queues"] = assigned_queues

        extra_filters = " ".join(filter_clauses)

        claim_query = text(f"""
        WITH candidate_job AS (
            SELECT j.id
            FROM jobs j
            JOIN queues q ON j.queue_id = q.id
            WHERE j.status = 'queued'
              AND j.run_at <= NOW()
              AND q.is_paused = FALSE
              {extra_filters}
              AND (
                  SELECT COUNT(*)
                  FROM jobs active_j
                  WHERE active_j.queue_id = q.id 
                    AND active_j.status = 'running'
              ) < q.concurrency_limit
            ORDER BY q.priority DESC, j.priority DESC, j.run_at ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        )
        UPDATE jobs
        SET status = 'running',
            locked_by_worker_id = :worker_id,
            lock_expires_at = NOW() + (:lock_seconds * INTERVAL '1 second'),
            started_at = NOW(),
            claimed_at = NOW(),
            attempt_count = attempt_count + 1,
            updated_at = NOW()
        WHERE id IN (SELECT id FROM candidate_job)
        RETURNING id;
        """)

        result = await session.execute(claim_query, params)
        row = result.fetchone()

        if not row:
            return None

        claimed_job_id = row[0]

        # Query job with fresh state and loaded relationships
        stmt = (
            select(Job)
            .options(selectinload(Job.queue).selectinload(Queue.retry_policy))
            .where(Job.id == claimed_job_id)
            .execution_options(populate_existing=True)
        )
        res = await session.execute(stmt)
        job = res.scalar_one()

        # 🪣 Enforce Token-Bucket Rate Limiter per Queue
        if job.queue and job.queue.rate_limit_rps:
            allowed = await QueueRateLimiter.allow_claim(job.queue.id, job.queue.rate_limit_rps)
            if not allowed:
                # Rate limit exceeded for this second -> Revert lock and release
                job.status = "queued"
                job.locked_by_worker_id = None
                job.lock_expires_at = None
                job.attempt_count = max(0, job.attempt_count - 1)
                job.started_at = None
                job.claimed_at = None
                await session.commit()
                return None

        await session.commit()
        return job
