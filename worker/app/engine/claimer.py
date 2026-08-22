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
    Executes atomic queue polling with queue-level row locking serialization
    and PostgreSQL's `FOR UPDATE SKIP LOCKED`.
    Guarantees strict zero-double-execution, strictly atomic queue concurrency limits,
    priority ordering, pause flags, and token-bucket rate limits in ACID transactions.
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
        Atomically selects and claims the highest priority ready job while strictly
        enforcing queue-level concurrency limits using queue row serialization (`FOR UPDATE`).
        Enforces token-bucket rate limits per queue.
        """
        if queue_id:
            candidate_queue_ids = [queue_id]
        else:
            filter_clauses = ["q.is_paused = FALSE"]
            q_params = {}

            if assigned_queues and len(assigned_queues) > 0:
                filter_clauses.append("q.name = ANY(:assigned_queues)")
                q_params["assigned_queues"] = assigned_queues

            where_clause = " AND ".join(filter_clauses)

            candidate_queues_query = text(f"""
            SELECT q.id
            FROM queues q
            WHERE {where_clause}
              AND EXISTS (
                  SELECT 1 FROM jobs j
                  WHERE j.queue_id = q.id
                    AND j.status = 'queued'
                    AND j.run_at <= NOW()
              )
            ORDER BY q.priority DESC, q.created_at ASC
            """)

            res_q = await session.execute(candidate_queues_query, q_params)
            candidate_queue_ids = [r[0] for r in res_q.fetchall()]

        if not candidate_queue_ids:
            return None

        for target_queue_id in candidate_queue_ids:
            # 1. Lock queue row for update to serialize claiming on this queue
            lock_q_stmt = text("""
                SELECT id, concurrency_limit, is_paused, rate_limit_rps
                FROM queues
                WHERE id = :target_queue_id
                FOR UPDATE
            """)
            q_res = await session.execute(lock_q_stmt, {"target_queue_id": target_queue_id})
            queue_row = q_res.fetchone()

            if not queue_row:
                continue

            q_id, concurrency_limit, is_paused, rate_limit_rps = queue_row

            if is_paused:
                continue

            # 2. Check running count under the fresh snapshot (guaranteed latest committed state)
            count_stmt = text("""
                SELECT COUNT(*)
                FROM jobs
                WHERE queue_id = :target_queue_id
                  AND status = 'running'
                  AND (lock_expires_at IS NULL OR lock_expires_at > NOW())
            """)
            c_res = await session.execute(count_stmt, {"target_queue_id": target_queue_id})
            running_count = c_res.scalar() or 0

            if running_count >= concurrency_limit:
                # Queue is at capacity; check next candidate queue
                continue

            # 3. Find and claim the next available job with fresh lease fencing token
            lease_token = uuid.uuid4()
            claim_stmt = text("""
                WITH candidate AS (
                    SELECT id
                    FROM jobs
                    WHERE queue_id = :target_queue_id
                      AND status = 'queued'
                      AND run_at <= NOW()
                    ORDER BY priority DESC, run_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE jobs
                SET status = 'running',
                    locked_by_worker_id = :worker_id,
                    lease_token = :lease_token,
                    lock_expires_at = NOW() + (:lock_seconds * INTERVAL '1 second'),
                    started_at = NOW(),
                    claimed_at = NOW(),
                    attempt_count = attempt_count + 1,
                    updated_at = NOW()
                WHERE id IN (SELECT id FROM candidate)
                RETURNING id;
            """)
            claim_params = {
                "target_queue_id": target_queue_id,
                "worker_id": worker_id,
                "lease_token": lease_token,
                "lock_seconds": lock_timeout_seconds,
            }
            res_job = await session.execute(claim_stmt, claim_params)
            job_row = res_job.fetchone()

            if not job_row:
                # No ready jobs available in this queue
                continue

            claimed_job_id = job_row[0]

            # 4. Load full job entity with relations
            stmt = (
                select(Job)
                .options(selectinload(Job.queue).selectinload(Queue.retry_policy))
                .where(Job.id == claimed_job_id)
                .execution_options(populate_existing=True)
            )
            res = await session.execute(stmt)
            job = res.scalar_one()

            # 🪣 Enforce Token-Bucket Rate Limiter per Queue
            if rate_limit_rps:
                allowed = await QueueRateLimiter.allow_claim(target_queue_id, rate_limit_rps)
                if not allowed:
                    # Rate limit exceeded for this second -> Revert lock and release
                    job.status = "queued"
                    job.locked_by_worker_id = None
                    job.lease_token = None
                    job.lock_expires_at = None
                    job.attempt_count = max(0, job.attempt_count - 1)
                    job.started_at = None
                    job.claimed_at = None
                    await session.commit()
                    return None

            await session.commit()
            return job

        await session.commit()
        return None
