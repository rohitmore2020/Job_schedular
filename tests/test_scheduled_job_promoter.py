import pytest
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func

from backend.app.core.database import AsyncSessionLocal
from backend.app.models import (
    Organization,
    Project,
    Queue,
    Job,
    JobStatus,
    ExecutionStatus,
)
from worker.app.engine.claimer import AtomicClaimer
from worker.app.engine.runner import TaskRunner
from worker.app.promoter import ScheduledJobPromoter


@pytest.fixture
async def promoter_env():
    """Sets up an isolated Organization, Project, and Queue for promoter testing."""
    async with AsyncSessionLocal() as session:
        org = Organization(name="Promoter Org", slug=f"prom-org-{uuid.uuid4().hex[:6]}")
        session.add(org)
        await session.flush()

        project = Project(
            org_id=org.id,
            name="Promoter Project",
            slug=f"prom-proj-{uuid.uuid4().hex[:6]}",
        )
        session.add(project)
        await session.flush()

        queue = Queue(
            project_id=project.id,
            name=f"promoter-queue-{uuid.uuid4().hex[:6]}",
            priority=50,
            concurrency_limit=10,
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
# TEST 1 — Delayed Job Execution Flow
# Flow: POST -> SCHEDULED -> run_at reached -> Promoter -> QUEUED -> Claimer -> RUNNING -> COMPLETED
# =========================================================================
@pytest.mark.asyncio
async def test_delayed_job_execution(promoter_env):
    queue_id = promoter_env["queue_id"]
    queue_name = promoter_env["queue_name"]
    now_utc = datetime.now(timezone.utc)
    target_fire_time = now_utc + timedelta(seconds=1)

    # 1. Enqueue job with future run_at (Status = SCHEDULED)
    async with AsyncSessionLocal() as session:
        job = Job(
            queue_id=queue_id,
            name="delayed_invoice_task",
            status=JobStatus.SCHEDULED,
            payload={"invoice_id": 901},
            run_at=target_fire_time,
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    # 2. Before fire time, worker CANNOT claim the job
    async with AsyncSessionLocal() as session:
        unclaimed = await AtomicClaimer.claim_next_job(
            session, worker_id="worker-prom-1", assigned_queues=[queue_name]
        )
        assert unclaimed is None

    # 3. Wait for fire time to be reached
    await asyncio.sleep(1.1)

    # 4. ScheduledJobPromoter promotes the job: SCHEDULED -> QUEUED
    promoter = ScheduledJobPromoter(scan_interval_seconds=0.1)
    async with AsyncSessionLocal() as session:
        promoted_count = await promoter.promote_due_jobs(session, queue_id=queue_id)
        assert promoted_count == 1

    # Verify job status in DB is now QUEUED
    async with AsyncSessionLocal() as session:
        promoted_job = await session.get(Job, job_id)
        assert promoted_job.status == JobStatus.QUEUED

    # 5. AtomicClaimer claims the now-QUEUED job
    async with AsyncSessionLocal() as session:
        claimed_job = await AtomicClaimer.claim_next_job(
            session, worker_id="worker-prom-1", assigned_queues=[queue_name]
        )
        assert claimed_job is not None
        assert claimed_job.id == job_id
        assert claimed_job.status == JobStatus.RUNNING

        # 6. Worker executes and completes the job
        exec_res = await TaskRunner.execute_job(session, claimed_job, "worker-prom-1")
        assert exec_res.status == ExecutionStatus.SUCCESS

    # 7. Verify final DB state is COMPLETED
    async with AsyncSessionLocal() as session:
        final_job = await session.get(Job, job_id)
        assert final_job.status == JobStatus.COMPLETED


# =========================================================================
# TEST 2 — Delayed Job Batch Promotion
# =========================================================================
@pytest.mark.asyncio
async def test_delayed_job_promotion(promoter_env):
    queue_id = promoter_env["queue_id"]
    now_utc = datetime.now(timezone.utc)
    due_time = now_utc - timedelta(seconds=5)
    future_time = now_utc + timedelta(hours=1)

    async with AsyncSessionLocal() as session:
        # Create 10 due scheduled jobs
        for i in range(10):
            j = Job(
                queue_id=queue_id,
                name=f"due_job_{i}",
                status=JobStatus.SCHEDULED,
                payload={"index": i},
                run_at=due_time,
            )
            session.add(j)

        # Create 5 future scheduled jobs (not due yet)
        for i in range(5):
            j = Job(
                queue_id=queue_id,
                name=f"future_job_{i}",
                status=JobStatus.SCHEDULED,
                payload={"index": i},
                run_at=future_time,
            )
            session.add(j)

        await session.commit()

    promoter = ScheduledJobPromoter(scan_interval_seconds=0.1, batch_size=50)

    # Execute promoter sweep
    async with AsyncSessionLocal() as session:
        count = await promoter.promote_due_jobs(session, queue_id=queue_id)
        assert count == 10

    # Verify: 10 jobs are now QUEUED, 5 jobs remain SCHEDULED
    async with AsyncSessionLocal() as session:
        queued_count = await session.scalar(
            select(func.count(Job.id)).where(
                Job.queue_id == queue_id,
                Job.status == JobStatus.QUEUED,
            )
        )
        scheduled_count = await session.scalar(
            select(func.count(Job.id)).where(
                Job.queue_id == queue_id,
                Job.status == JobStatus.SCHEDULED,
            )
        )
        assert queued_count == 10
        assert scheduled_count == 5


# =========================================================================
# TEST 3 — Multiple Promoters HA Race Protection
# =========================================================================
@pytest.mark.asyncio
async def test_multiple_promoters(promoter_env):
    queue_id = promoter_env["queue_id"]
    now_utc = datetime.now(timezone.utc)
    due_time = now_utc - timedelta(seconds=10)

    # Enqueue 30 due scheduled jobs
    async with AsyncSessionLocal() as session:
        for i in range(30):
            j = Job(
                queue_id=queue_id,
                name=f"ha_prom_job_{i}",
                status=JobStatus.SCHEDULED,
                payload={"i": i},
                run_at=due_time,
            )
            session.add(j)
        await session.commit()

    # Create 3 independent promoter daemon instances
    prom_a = ScheduledJobPromoter(scan_interval_seconds=0.1)
    prom_b = ScheduledJobPromoter(scan_interval_seconds=0.1)
    prom_c = ScheduledJobPromoter(scan_interval_seconds=0.1)

    async def run_promoter(p):
        async with AsyncSessionLocal() as session:
            return await p.promote_due_jobs(session, queue_id=queue_id)

    # Concurrently sweep with all 3 promoters
    results = await asyncio.gather(
        run_promoter(prom_a),
        run_promoter(prom_b),
        run_promoter(prom_c),
    )

    total_promoted = sum(results)
    assert total_promoted == 30, f"Expected exactly 30 total promotions across 3 promoters, got {total_promoted}"

    # Verify in DB that all 30 are QUEUED with zero duplicates
    async with AsyncSessionLocal() as session:
        queued_count = await session.scalar(
            select(func.count(Job.id)).where(
                Job.queue_id == queue_id,
                Job.status == JobStatus.QUEUED,
            )
        )
        scheduled_count = await session.scalar(
            select(func.count(Job.id)).where(
                Job.queue_id == queue_id,
                Job.status == JobStatus.SCHEDULED,
            )
        )
        assert queued_count == 30
        assert scheduled_count == 0


# =========================================================================
# TEST 4 — Scheduled Job Race with Concurrent Ingestion & Claims
# =========================================================================
@pytest.mark.asyncio
async def test_scheduled_job_race(promoter_env):
    queue_id = promoter_env["queue_id"]
    queue_name = promoter_env["queue_name"]
    now_utc = datetime.now(timezone.utc)
    due_time = now_utc - timedelta(milliseconds=100)

    # 1. Concurrently enqueue 20 scheduled jobs
    async with AsyncSessionLocal() as session:
        for i in range(20):
            j = Job(
                queue_id=queue_id,
                name=f"race_task_{i}",
                status=JobStatus.SCHEDULED,
                payload={"index": i},
                run_at=due_time,
            )
            session.add(j)
        await session.commit()

    promoter = ScheduledJobPromoter(scan_interval_seconds=0.05)

    # 2. Concurrently run 2 promoters and 3 workers draining the queue
    promoted_total = 0
    executed_total = 0

    async def promoter_worker():
        nonlocal promoted_total
        for _ in range(5):
            async with AsyncSessionLocal() as session:
                promoted_total += await promoter.promote_due_jobs(session)
            await asyncio.sleep(0.01)

    async def task_worker(worker_id: str):
        nonlocal executed_total
        while True:
            async with AsyncSessionLocal() as session:
                job = await AtomicClaimer.claim_next_job(
                    session, worker_id=worker_id, assigned_queues=[queue_name]
                )
                if not job:
                    # Check if all completed
                    done_count = await session.scalar(
                        select(func.count(Job.id)).where(
                            Job.queue_id == queue_id,
                            Job.status == JobStatus.COMPLETED,
                        )
                    )
                    if done_count == 20:
                        break
                    await asyncio.sleep(0.01)
                    continue

                exec_res = await TaskRunner.execute_job(session, job, worker_id)
                if exec_res.status == ExecutionStatus.SUCCESS:
                    executed_total += 1

    await asyncio.gather(
        promoter_worker(),
        promoter_worker(),
        task_worker("worker-race-1"),
        task_worker("worker-race-2"),
        task_worker("worker-race-3"),
    )

    # 3. Assert all 20 jobs executed cleanly to COMPLETED with 0 failures
    assert executed_total == 20
    async with AsyncSessionLocal() as session:
        completed_count = await session.scalar(
            select(func.count(Job.id)).where(
                Job.queue_id == queue_id,
                Job.status == JobStatus.COMPLETED,
            )
        )
        assert completed_count == 20
