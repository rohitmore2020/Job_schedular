import pytest
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from backend.app.models import (
    Organization,
    Project,
    Queue,
    Job,
    DLQEntry,
    Worker,
    WorkerHeartbeat,
    JobStatus,
    WorkerStatus,
    ExecutionStatus,
)
from worker.app.engine.claimer import AtomicClaimer
from worker.app.engine.runner import TaskRunner
from worker.app.heartbeat import WorkerHeartbeatEmitter
from worker.app.reaper import LeaseReaper


@pytest.fixture
async def queue_fixture(db_session):
    org = Organization(name="Reaper Test Org", slug=f"reaper-org-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    proj = Project(org_id=org.id, name="Reaper Proj", slug=f"r-proj-{uuid.uuid4().hex[:6]}")
    db_session.add(proj)
    await db_session.flush()

    queue = Queue(
        project_id=proj.id,
        name=f"reaper-queue-{uuid.uuid4().hex[:6]}",
        priority=50,
        concurrency_limit=10,
        is_paused=False,
    )
    db_session.add(queue)
    await db_session.commit()
    await db_session.refresh(queue)
    return queue


@pytest.mark.asyncio
async def test_heartbeat_emitter_telemetry(db_session, queue_fixture):
    """Verify heartbeat emitter writes CPU/RAM stats and extends job lease locks."""
    queue = queue_fixture
    worker_id = f"worker-hb-{uuid.uuid4().hex[:6]}"

    # Register worker
    worker = Worker(
        worker_id=worker_id,
        hostname="test-host",
        pid=9999,
        concurrency_limit=5,
        status=WorkerStatus.ALIVE,
        assigned_queues=[queue.name],
        started_at=datetime.now(timezone.utc),
        last_heartbeat_at=datetime.now(timezone.utc),
    )
    db_session.add(worker)

    # Add active running job
    now_utc = datetime.now(timezone.utc)
    job = Job(
        queue_id=queue.id,
        name="send_email",
        status=JobStatus.RUNNING,
        locked_by_worker_id=worker_id,
        lock_expires_at=now_utc + timedelta(seconds=10),
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    # Initialize emitter and emit using session
    active_ids = {job.id}
    emitter = WorkerHeartbeatEmitter(worker_id, active_ids)
    metrics = await emitter.emit_once(db_session)

    assert metrics["worker_id"] == worker_id
    assert metrics["active_jobs"] == 1
    assert metrics["memory_mb"] > 0

    # Verify lease lock extended in DB
    await db_session.refresh(job)
    assert job.lock_expires_at > now_utc + timedelta(seconds=20)


@pytest.mark.asyncio
async def test_zombie_worker_and_lease_reaper_recovery(db_session, queue_fixture):
    """
    CRITICAL RECOVERY TEST:
    1. Worker A claims a job.
    2. Worker A crashes (lease expires in past).
    3. LeaseReaper runs sweep.
    4. Assert job is reset to 'queued' with lease expiration reason.
    5. Healthy Worker B claims the recovered job and completes it successfully.
    """
    queue = queue_fixture
    job = Job(
        queue_id=queue.id,
        name="send_email",
        status=JobStatus.QUEUED,
        payload={"email": "crashed_worker@example.com"},
        max_retries=3,
    )
    db_session.add(job)
    await db_session.commit()

    # Step 1: Worker A claims the job
    worker_a_id = "crashed-worker-node-1"
    claimed_job = await AtomicClaimer.claim_next_job(
        db_session, worker_a_id, assigned_queues=[queue.name]
    )
    assert claimed_job is not None
    assert claimed_job.status == JobStatus.RUNNING
    assert claimed_job.locked_by_worker_id == worker_a_id

    # Step 2: Simulate Worker A crash (expire its lease into the past)
    claimed_job.lock_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    await db_session.commit()

    # Step 3: Run LeaseReaper sweep
    reaper = LeaseReaper()
    reap_summary = await reaper.reap_expired_leases(db_session)
    assert reap_summary["jobs_requeued"] >= 1

    # Step 4: Verify Job is recovered back to 'queued'
    await db_session.refresh(claimed_job)
    assert claimed_job.status == JobStatus.QUEUED
    assert claimed_job.locked_by_worker_id is None
    assert claimed_job.lock_expires_at is None
    assert "Worker lease expired" in claimed_job.error_message

    # Step 5: Healthy Worker B claims the recovered job and finishes it
    worker_b_id = "healthy-worker-node-2"
    reclaimed_job = await AtomicClaimer.claim_next_job(
        db_session, worker_b_id, assigned_queues=[queue.name]
    )
    assert reclaimed_job is not None
    assert reclaimed_job.id == claimed_job.id
    assert reclaimed_job.locked_by_worker_id == worker_b_id

    execution = await TaskRunner.execute_job(db_session, reclaimed_job, worker_b_id)
    assert execution.status == ExecutionStatus.SUCCESS
    assert reclaimed_job.status == JobStatus.COMPLETED


@pytest.mark.asyncio
async def test_reaper_escalates_to_dlq_when_retries_exhausted(db_session, queue_fixture):
    """Verify reaper routes expired jobs to DLQ if max_retries has been reached."""
    queue = queue_fixture
    now_utc = datetime.now(timezone.utc)

    # Job already at attempt 3 of 3
    job = Job(
        queue_id=queue.id,
        name="process_video",
        status=JobStatus.RUNNING,
        attempt_count=3,
        max_retries=3,
        locked_by_worker_id="crashed-worker-exhausted",
        lock_expires_at=now_utc - timedelta(seconds=15),
    )
    db_session.add(job)
    await db_session.commit()

    reaper = LeaseReaper()
    summary = await reaper.reap_expired_leases(db_session)
    assert summary["jobs_moved_to_dlq"] >= 1

    await db_session.refresh(job)
    assert job.status == JobStatus.DEAD_LETTER

    # Verify DLQ entry created
    dlq_res = await db_session.execute(
        select(DLQEntry).where(DLQEntry.job_id == job.id)
    )
    dlq = dlq_res.scalar_one_or_none()
    assert dlq is not None
    assert dlq.total_attempts == 3
    assert "Worker lease expired" in dlq.failed_reason


@pytest.mark.asyncio
async def test_worker_rest_api_endpoints(client):
    """Verify /workers and /workers/{id}/heartbeats REST endpoints."""
    # Authenticate
    email = f"worker-admin-{uuid.uuid4().hex[:6]}@test.com"
    signup_res = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": "W Admin", "organization_name": "W Org"},
    )
    token = signup_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # List workers
    workers_res = await client.get("/api/v1/workers", headers=headers)
    assert workers_res.status_code == 200
    workers_list = workers_res.json()
    assert len(workers_list) >= 1
    worker_id = workers_list[0]["worker_id"]

    # Get heartbeats
    hb_res = await client.get(f"/api/v1/workers/{worker_id}/heartbeats", headers=headers)
    assert hb_res.status_code == 200
    assert isinstance(hb_res.json(), list)
