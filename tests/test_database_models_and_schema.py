import pytest
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.app.models import (
    Organization,
    User,
    Project,
    Queue,
    RetryPolicy,
    Job,
    JobExecution,
    ScheduledJob,
    DLQEntry,
    Worker,
    WorkerHeartbeat,
    UserRole,
    JobStatus,
    RetryStrategy,
    WorkerStatus,
    ExecutionStatus,
)
from backend.app.core.security import hash_password


@pytest.mark.asyncio
async def test_org_project_user_hierarchy(db_session):
    """Test creating an Organization with nested Users and Projects."""
    org = Organization(name="Test Corp", slug=f"test-corp-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    user = User(
        org_id=org.id,
        email=f"tester-{uuid.uuid4().hex[:6]}@test.com",
        hashed_password=hash_password("secretpass"),
        full_name="Test User",
        role=UserRole.ADMIN,
    )
    project = Project(
        org_id=org.id,
        name="Primary Project",
        slug=f"primary-proj-{uuid.uuid4().hex[:6]}",
    )
    db_session.add_all([user, project])
    await db_session.commit()

    # Query back
    result = await db_session.execute(
        select(Organization).where(Organization.id == org.id)
    )
    fetched_org = result.scalar_one()
    assert fetched_org.name == "Test Corp"


@pytest.mark.asyncio
async def test_queue_and_retry_policy(db_session):
    """Test creating a Queue with custom RetryPolicy."""
    org = Organization(name="Queue Corp", slug=f"queue-corp-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    proj = Project(org_id=org.id, name="Q Project", slug=f"q-proj-{uuid.uuid4().hex[:6]}")
    db_session.add(proj)
    await db_session.flush()

    queue = Queue(
        project_id=proj.id,
        name="high-priority-queue",
        priority=80,
        concurrency_limit=15,
        rate_limit_rps=50,
    )
    db_session.add(queue)
    await db_session.flush()

    policy = RetryPolicy(
        queue_id=queue.id,
        strategy=RetryStrategy.EXPONENTIAL,
        max_retries=5,
        initial_interval_sec=2,
        max_interval_sec=120,
        backoff_multiplier=2.5,
        jitter=True,
    )
    db_session.add(policy)
    await db_session.commit()

    res = await db_session.execute(select(Queue).where(Queue.id == queue.id))
    fetched_q = res.scalar_one()
    assert fetched_q.priority == 80
    assert fetched_q.concurrency_limit == 15


@pytest.mark.asyncio
async def test_job_idempotency_constraint(db_session):
    """Test that duplicate idempotency_key in the same queue raises IntegrityError."""
    org = Organization(name="Idempotent Org", slug=f"idem-org-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    proj = Project(org_id=org.id, name="Idem Proj", slug=f"idem-proj-{uuid.uuid4().hex[:6]}")
    db_session.add(proj)
    await db_session.flush()

    queue = Queue(project_id=proj.id, name="idem-queue")
    db_session.add(queue)
    await db_session.flush()

    idempotency_token = f"idem-key-{uuid.uuid4().hex}"

    job1 = Job(
        queue_id=queue.id,
        name="process_payment",
        idempotency_key=idempotency_token,
        payload={"amount": 100},
    )
    db_session.add(job1)
    await db_session.commit()

    # Second job with same idempotency_key in same queue must fail
    job2 = Job(
        queue_id=queue.id,
        name="process_payment",
        idempotency_key=idempotency_token,
        payload={"amount": 100},
    )
    db_session.add(job2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_job_lifecycle_and_executions(db_session):
    """Test transitions of a job with execution telemetry logs."""
    org = Organization(name="Exec Org", slug=f"exec-org-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    proj = Project(org_id=org.id, name="Exec Proj", slug=f"exec-proj-{uuid.uuid4().hex[:6]}")
    db_session.add(proj)
    await db_session.flush()

    queue = Queue(project_id=proj.id, name="exec-queue")
    db_session.add(queue)
    await db_session.flush()

    job = Job(
        queue_id=queue.id,
        name="render_thumbnail",
        status=JobStatus.QUEUED,
        payload={"width": 300, "height": 300},
    )
    db_session.add(job)
    await db_session.flush()

    # Worker claims and completes job
    now = datetime.now(timezone.utc)
    job.status = JobStatus.RUNNING
    job.locked_by_worker_id = "worker-test-01"
    job.started_at = now
    job.attempt_count = 1
    await db_session.flush()

    execution = JobExecution(
        job_id=job.id,
        worker_id="worker-test-01",
        attempt_number=1,
        status=ExecutionStatus.SUCCESS,
        started_at=now,
        finished_at=now + timedelta(milliseconds=150),
        duration_ms=150,
        logs="[INFO] Thumbnail generated 300x300",
    )
    db_session.add(execution)

    job.status = JobStatus.COMPLETED
    job.completed_at = execution.finished_at
    job.result = {"url": "https://cdn.example.com/thumb.jpg"}
    await db_session.commit()

    # Query back
    res = await db_session.execute(select(Job).where(Job.id == job.id))
    fetched_job = res.scalar_one()
    assert fetched_job.status == JobStatus.COMPLETED
    assert fetched_job.result["url"] == "https://cdn.example.com/thumb.jpg"


@pytest.mark.asyncio
async def test_worker_and_heartbeats(db_session):
    """Test worker registration and telemetry heartbeats."""
    worker_id = f"worker-test-{uuid.uuid4().hex[:6]}"
    worker = Worker(
        worker_id=worker_id,
        hostname="test-host.local",
        pid=12345,
        concurrency_limit=8,
        status=WorkerStatus.ALIVE,
        assigned_queues=["default", "urgent"],
        started_at=datetime.now(timezone.utc),
        last_heartbeat_at=datetime.now(timezone.utc),
    )
    db_session.add(worker)
    await db_session.flush()

    hb = WorkerHeartbeat(
        worker_id=worker.worker_id,
        cpu_percent=12.5,
        memory_mb=256.0,
        active_jobs=2,
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(hb)
    await db_session.commit()

    res = await db_session.execute(select(Worker).where(Worker.worker_id == worker_id))
    fetched_worker = res.scalar_one()
    assert fetched_worker.concurrency_limit == 8
    assert fetched_worker.status == WorkerStatus.ALIVE
