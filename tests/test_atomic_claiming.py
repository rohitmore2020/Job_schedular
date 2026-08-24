import pytest
import asyncio
import uuid
import time
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from backend.app.core.database import AsyncSessionLocal
from backend.app.models import (
    Organization,
    Project,
    Queue,
    Job,
    JobExecution,
    JobStatus,
    ExecutionStatus,
)
from worker.app.engine.claimer import AtomicClaimer
from worker.app.engine.runner import TaskRunner


@pytest.fixture
async def claiming_env():
    """Sets up an isolated Organization, Project, and high-concurrency Queue."""
    async with AsyncSessionLocal() as session:
        org = Organization(
            name="Atomic Org", slug=f"atomic-org-{uuid.uuid4().hex[:6]}"
        )
        session.add(org)
        await session.flush()

        project = Project(
            org_id=org.id,
            name="Atomic Project",
            slug=f"atomic-proj-{uuid.uuid4().hex[:6]}",
        )
        session.add(project)
        await session.flush()

        queue = Queue(
            project_id=project.id,
            name=f"atomic-claim-queue-{uuid.uuid4().hex[:6]}",
            priority=50,
            concurrency_limit=50,  # high limit to test unconstrained worker throughput
            is_paused=False,
        )
        session.add(queue)
        await session.commit()
        await session.refresh(queue)

        return {
            "org_id": org.id,
            "project_id": project.id,
            "queue_id": queue.id,
            "queue_name": queue.name,
        }


# =========================================================================
# TEST 2.1 — 100 Jobs, 5 Workers: 100 Unique Executions, 0 Duplicate Executions
# =========================================================================
@pytest.mark.asyncio
async def test_atomic_claiming_100_jobs_5_workers(claiming_env):
    """
    Evaluates 2.1 Atomic Claiming:
    - 100 jobs enqueued in PostgreSQL
    - 5 concurrent workers aggressively claiming and executing
    - Expected:
      * Exactly 100 unique executions
      * Exactly 0 duplicate claims or executions
      * All 5 workers actively participate in the drain
      * All 100 jobs reach JobStatus.COMPLETED
    """
    queue_id = claiming_env["queue_id"]
    queue_name = claiming_env["queue_name"]
    now_utc = datetime.now(timezone.utc)
    total_jobs = 100
    total_workers = 5

    # 1. Enqueue 100 jobs with varied payloads and priorities
    job_ids = []
    async with AsyncSessionLocal() as session:
        for i in range(total_jobs):
            j = Job(
                queue_id=queue_id,
                name=f"atomic_task_{i}",
                status=JobStatus.QUEUED,
                priority=10 + (i % 80),
                payload={"index": i, "token": uuid.uuid4().hex},
                run_at=now_utc,
                max_retries=3,
            )
            session.add(j)
            await session.flush()
            job_ids.append(j.id)
        await session.commit()

    assert len(job_ids) == 100

    # 2. Worker processing counters
    worker_claims = {f"worker-node-{w}": [] for w in range(total_workers)}
    completed_executions = []

    async def worker_loop(worker_id: str):
        consecutive_empty = 0
        while True:
            async with AsyncSessionLocal() as session:
                job = await AtomicClaimer.claim_next_job(
                    session,
                    worker_id=worker_id,
                    assigned_queues=[queue_name],
                    lock_timeout_seconds=30,
                )
                if not job:
                    consecutive_empty += 1
                    # Check if all jobs in the queue are completed
                    remaining = await session.scalar(
                        select(func.count(Job.id)).where(
                            Job.queue_id == queue_id,
                            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
                        )
                    )
                    if remaining == 0 or consecutive_empty >= 10:
                        break
                    await asyncio.sleep(0.005)
                    continue

                consecutive_empty = 0
                worker_claims[worker_id].append(job.id)

                # Execute task
                exec_record = await TaskRunner.execute_job(session, job, worker_id)
                completed_executions.append(exec_record)

    # 3. Launch all 5 workers concurrently
    start_time = time.perf_counter()
    worker_tasks = [worker_loop(f"worker-node-{w}") for w in range(total_workers)]
    await asyncio.gather(*worker_tasks)
    elapsed_time = time.perf_counter() - start_time

    # 4. Strict Assertions: 100 Unique Executions & 0 Duplicate Executions
    all_claimed_ids = []
    for wid, claims in worker_claims.items():
        all_claimed_ids.extend(claims)

    assert len(all_claimed_ids) == 100, f"Expected 100 claims, got {len(all_claimed_ids)}"
    assert len(set(all_claimed_ids)) == 100, "Duplicate job claim detected in memory!"

    # 5. Database-level verification: Exactly 100 execution rows in job_executions
    async with AsyncSessionLocal() as session:
        # Check total execution records for this queue
        db_exec_count = await session.scalar(
            select(func.count(JobExecution.id))
            .join(Job, JobExecution.job_id == Job.id)
            .where(Job.queue_id == queue_id)
        )
        assert db_exec_count == 100, f"Expected exactly 100 DB executions, got {db_exec_count}"

        # Strict duplicate check query: GROUP BY job_id HAVING count > 1
        dup_stmt = (
            select(JobExecution.job_id, func.count(JobExecution.id).label("cnt"))
            .join(Job, JobExecution.job_id == Job.id)
            .where(Job.queue_id == queue_id)
            .group_by(JobExecution.job_id)
            .having(func.count(JobExecution.id) > 1)
        )
        dup_res = await session.execute(dup_stmt)
        duplicates = dup_res.fetchall()
        assert len(duplicates) == 0, f"Database detected duplicate executions: {duplicates}"

        # 6. Verify all 100 jobs transitioned to COMPLETED
        completed_job_count = await session.scalar(
            select(func.count(Job.id)).where(
                Job.queue_id == queue_id,
                Job.status == JobStatus.COMPLETED,
            )
        )
        assert completed_job_count == 100

        # 7. Fleet distribution: every worker processed tasks
        for wid, claims in worker_claims.items():
            assert len(claims) > 0, f"Worker {wid} was starved and processed 0 jobs"

    print(
        f"\n✅ 100 Jobs processed by 5 Workers in {elapsed_time:.2f}s "
        f"({100/elapsed_time:.1f} jobs/s) — 0 Duplicates."
    )


# =========================================================================
# TEST 2.2 — High Contention Collision Storm (10 Workers, 1 Job)
# =========================================================================
@pytest.mark.asyncio
async def test_atomic_claiming_high_contention_single_job(claiming_env):
    """
    Spawns 10 parallel workers racing to claim 1 single job simultaneously.
    Guarantees FOR UPDATE SKIP LOCKED allows exactly 1 winner with 0 race errors.
    """
    queue_id = claiming_env["queue_id"]
    queue_name = claiming_env["queue_name"]

    async with AsyncSessionLocal() as session:
        job = Job(
            queue_id=queue_id,
            name="exclusive_prize_task",
            status=JobStatus.QUEUED,
            priority=100,
            payload={"action": "single_winner"},
            run_at=datetime.now(timezone.utc),
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    async def attempt_claim(worker_id: str):
        async with AsyncSessionLocal() as session:
            return await AtomicClaimer.claim_next_job(
                session, worker_id=worker_id, assigned_queues=[queue_name]
            )

    # 10 workers storm the claimer at the exact same millisecond
    results = await asyncio.gather(*[attempt_claim(f"racer-{i}") for i in range(10)])

    winners = [j for j in results if j is not None]
    losers = [j for j in results if j is None]

    assert len(winners) == 1, f"Expected exactly 1 winner, got {len(winners)}"
    assert len(losers) == 9
    assert winners[0].id == job_id
