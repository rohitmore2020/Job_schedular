import pytest
import uuid
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select, func

from backend.app.models import (
    Organization,
    Project,
    Queue,
    Job,
    JobExecution,
    DLQEntry,
    JobStatus,
    ExecutionStatus,
)
from worker.app.engine.claimer import AtomicClaimer
from worker.app.engine.runner import TaskRunner
from worker.app.engine.daemon import WorkerDaemon


@pytest.fixture
async def queue_fixture(db_session):
    """Create a dedicated test organization, project, and queue."""
    org = Organization(name="Worker Test Org", slug=f"worker-org-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    proj = Project(org_id=org.id, name="Worker Proj", slug=f"w-proj-{uuid.uuid4().hex[:6]}")
    db_session.add(proj)
    await db_session.flush()

    queue = Queue(
        project_id=proj.id,
        name=f"test-queue-{uuid.uuid4().hex[:6]}",
        priority=50,
        concurrency_limit=10,
        is_paused=False,
    )
    db_session.add(queue)
    await db_session.commit()
    await db_session.refresh(queue)
    return queue


@pytest.mark.asyncio
async def test_single_worker_claim_and_execute(db_session, queue_fixture):
    """Verify single worker claiming and successfully executing jobs."""
    queue = queue_fixture

    # Create 3 jobs
    for i in range(3):
        job = Job(
            queue_id=queue.id,
            name="send_email",
            status=JobStatus.QUEUED,
            payload={"email": f"client{i}@example.com", "subject": "Invoice"},
        )
        db_session.add(job)
    await db_session.commit()

    worker_id = "test-worker-alpha"

    # Claim and execute all 3 from this specific queue
    for _ in range(3):
        claimed_job = await AtomicClaimer.claim_next_job(
            db_session, worker_id, assigned_queues=[queue.name]
        )
        assert claimed_job is not None
        assert claimed_job.status == JobStatus.RUNNING
        assert claimed_job.locked_by_worker_id == worker_id

        execution = await TaskRunner.execute_job(db_session, claimed_job, worker_id)
        assert execution.status == ExecutionStatus.SUCCESS
        assert execution.duration_ms >= 1
        assert execution.logs is not None
        assert "Delivering email to" in execution.logs
        assert claimed_job.status == JobStatus.COMPLETED

    # Queue should now have 0 ready jobs
    no_job = await AtomicClaimer.claim_next_job(
        db_session, worker_id, assigned_queues=[queue.name]
    )
    assert no_job is None


@pytest.mark.asyncio
async def test_concurrent_worker_racing_no_duplicates(db_session, queue_fixture):
    """
    CRITICAL CONCURRENCY TEST:
    Spawn 10 parallel worker coroutines attempting to claim 30 jobs simultaneously.
    Asserts ZERO double execution, ZERO deadlocks, and EXACTLY 30 unique job completions.
    """
    queue = queue_fixture
    total_jobs = 30

    # Insert 30 jobs
    jobs = [
        Job(
            queue_id=queue.id,
            name="calculate_report",
            status=JobStatus.QUEUED,
            payload={"report_type": f"report_num_{i}"},
            priority=10 + (i % 5),
        )
        for i in range(total_jobs)
    ]
    db_session.add_all(jobs)
    await db_session.commit()

    async def worker_task(worker_num: int):
        worker_id = f"racing-worker-{worker_num}"
        daemon = WorkerDaemon(
            worker_id=worker_id,
            concurrency=1,
            assigned_queues=[queue.name],
        )

        while True:
            did_work = await daemon.run_once()
            if not did_work:
                break

    # Spawn 10 concurrent worker coroutines
    worker_coroutines = [worker_task(w) for w in range(10)]
    await asyncio.gather(*worker_coroutines)

    # Verify Database State:
    # 1. Total completed jobs must be exactly 30
    res_completed = await db_session.execute(
        select(func.count(Job.id)).where(
            Job.queue_id == queue.id,
            Job.status == JobStatus.COMPLETED,
        )
    )
    completed_count = res_completed.scalar()
    assert completed_count == total_jobs

    # 2. Total executions must be exactly 30 (no double executions)
    res_exec = await db_session.execute(
        select(func.count(JobExecution.id))
        .join(Job, JobExecution.job_id == Job.id)
        .where(Job.queue_id == queue.id)
    )
    exec_count = res_exec.scalar()
    assert exec_count == total_jobs


@pytest.mark.asyncio
async def test_worker_skips_paused_queue(db_session, queue_fixture):
    """Verify worker skips queues when is_paused = True."""
    queue = queue_fixture

    # Add job and pause queue
    job = Job(
        queue_id=queue.id,
        name="send_email",
        status=JobStatus.QUEUED,
        payload={"email": "pause_test@example.com"},
    )
    db_session.add(job)
    queue.is_paused = True
    await db_session.commit()

    # Attempt claim
    worker_id = "test-worker-pause"
    claimed = await AtomicClaimer.claim_next_job(
        db_session, worker_id, assigned_queues=[queue.name]
    )
    assert claimed is None

    # Resume queue
    queue.is_paused = False
    await db_session.commit()

    # Now claim should succeed
    resumed_claim = await AtomicClaimer.claim_next_job(
        db_session, worker_id, assigned_queues=[queue.name]
    )
    assert resumed_claim is not None
    assert resumed_claim.id == job.id


@pytest.mark.asyncio
async def test_worker_respects_queue_concurrency_limit(db_session, queue_fixture):
    """Verify worker respects queue-level max concurrency limits."""
    queue = queue_fixture
    queue.concurrency_limit = 2
    await db_session.commit()

    # Insert 3 jobs
    for i in range(3):
        j = Job(
            queue_id=queue.id,
            name="process_video",
            status=JobStatus.QUEUED,
            payload={"video_id": i},
        )
        db_session.add(j)
    await db_session.commit()

    # Worker 1 claims job 1
    w1_job = await AtomicClaimer.claim_next_job(
        db_session, "worker-1", assigned_queues=[queue.name]
    )
    assert w1_job is not None

    # Worker 2 claims job 2 (2/2 running)
    w2_job = await AtomicClaimer.claim_next_job(
        db_session, "worker-2", assigned_queues=[queue.name]
    )
    assert w2_job is not None

    # Worker 3 attempts to claim -> Should return None because limit of 2 is active
    w3_job = await AtomicClaimer.claim_next_job(
        db_session, "worker-3", assigned_queues=[queue.name]
    )
    assert w3_job is None

    # Finish job 1
    await TaskRunner.execute_job(db_session, w1_job, "worker-1")

    # Now Worker 3 should successfully claim the 3rd job
    w3_job_retry = await AtomicClaimer.claim_next_job(
        db_session, "worker-3", assigned_queues=[queue.name]
    )
    assert w3_job_retry is not None


@pytest.mark.asyncio
async def test_failing_task_captures_traceback_and_dlq(db_session, queue_fixture):
    """Verify failing task captures stack trace and moves to DLQ on max retries."""
    queue = queue_fixture

    failing_job = Job(
        queue_id=queue.id,
        name="mock_failing_task",
        status=JobStatus.QUEUED,
        payload={"error_type": "DivisionByZeroError"},
        max_retries=1,  # Exhaust retries on 1st attempt
    )
    db_session.add(failing_job)
    await db_session.commit()

    worker_id = "test-worker-fail"
    claimed = await AtomicClaimer.claim_next_job(
        db_session, worker_id, assigned_queues=[queue.name]
    )
    assert claimed is not None

    execution = await TaskRunner.execute_job(db_session, claimed, worker_id)
    assert execution.status == ExecutionStatus.FAILED
    assert "Simulated task failure" in execution.error_message
    assert "Traceback" in execution.stack_trace
    assert claimed.status == JobStatus.DEAD_LETTER

    # Verify DLQ entry
    dlq_res = await db_session.execute(
        select(DLQEntry).where(DLQEntry.job_id == claimed.id)
    )
    dlq = dlq_res.scalar_one_or_none()
    assert dlq is not None
    assert dlq.total_attempts == 1
    assert "Exhausted 1 retry attempts" in dlq.failed_reason
