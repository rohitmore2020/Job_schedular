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
async def lease_env():
    """Sets up an isolated Organization, Project, Queue, and Worker record."""
    async with AsyncSessionLocal() as session:
        org = Organization(name="Lease Org", slug=f"lease-org-{uuid.uuid4().hex[:6]}")
        session.add(org)
        await session.flush()

        project = Project(
            org_id=org.id,
            name="Lease Project",
            slug=f"lease-proj-{uuid.uuid4().hex[:6]}",
        )
        session.add(project)
        await session.flush()

        queue = Queue(
            project_id=project.id,
            name=f"lease-queue-{uuid.uuid4().hex[:6]}",
            priority=50,
            concurrency_limit=10,
            is_paused=False,
        )
        session.add(queue)
        await session.flush()

        worker_a = Worker(
            worker_id=f"worker-node-alpha-{uuid.uuid4().hex[:6]}",
            hostname="node-alpha.dc1.internal",
            pid=1001,
            status=WorkerStatus.ALIVE,
            current_active_jobs=0,
            assigned_queues=[queue.name],
            last_heartbeat_at=datetime.now(timezone.utc),
        )
        worker_b = Worker(
            worker_id=f"worker-node-beta-{uuid.uuid4().hex[:6]}",
            hostname="node-beta.dc1.internal",
            pid=1002,
            status=WorkerStatus.ALIVE,
            current_active_jobs=0,
            assigned_queues=[queue.name],
            last_heartbeat_at=datetime.now(timezone.utc),
        )
        session.add(worker_a)
        session.add(worker_b)
        await session.commit()

        return {
            "queue_id": queue.id,
            "queue_name": queue.name,
            "worker_a_id": worker_a.worker_id,
            "worker_b_id": worker_b.worker_id,
        }


# =========================================================================
# TEST 2.2A — Standard Lease Lifecycle: Claim -> Lease -> Heartbeat -> Renew -> Complete
# =========================================================================
@pytest.mark.asyncio
async def test_worker_lease_normal_lifecycle(lease_env):
    """
    Verifies normal lease lifecycle:
    1. Claim: Worker A acquires job atomically
    2. Lease: Job stamped with locked_by_worker_id, lease_token, lock_expires_at
    3. Heartbeat: Worker emits heartbeat telemetry
    4. Renew: Heartbeat emitter extends lock_expires_at for active in-flight jobs
    5. Complete: TaskRunner finalizes execution and releases lease
    """
    queue_id = lease_env["queue_id"]
    queue_name = lease_env["queue_name"]
    worker_id = lease_env["worker_a_id"]

    # 1. Enqueue job
    async with AsyncSessionLocal() as session:
        job = Job(
            queue_id=queue_id,
            name="send_welcome_email",
            status=JobStatus.QUEUED,
            payload={"user_id": 401},
            run_at=datetime.now(timezone.utc),
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    # 2. Claim job & verify lease tokens
    async with AsyncSessionLocal() as session:
        claimed = await AtomicClaimer.claim_next_job(
            session, worker_id=worker_id, assigned_queues=[queue_name], lock_timeout_seconds=15
        )
        assert claimed is not None
        assert claimed.id == job_id
        assert claimed.status == JobStatus.RUNNING
        assert claimed.locked_by_worker_id == worker_id
        assert claimed.lease_token is not None
        assert claimed.lock_expires_at is not None
        initial_expiration = claimed.lock_expires_at
        initial_lease_token = claimed.lease_token

    # 3 & 4. Heartbeat + Renew Lease
    active_jobs = {job_id}
    emitter = WorkerHeartbeatEmitter(worker_id=worker_id, active_job_ids_ref=active_jobs)
    await asyncio.sleep(0.1)

    async with AsyncSessionLocal() as session:
        hb_data = await emitter.emit_once(session)
        assert hb_data["worker_id"] == worker_id
        assert hb_data["active_jobs"] == 1
        await session.commit()

    # Verify lease was renewed further into the future
    async with AsyncSessionLocal() as session:
        renewed_job = await session.get(Job, job_id)
        assert renewed_job.lock_expires_at >= initial_expiration
        assert renewed_job.lease_token == initial_lease_token

    # 5. Complete execution and verify lease release
    async with AsyncSessionLocal() as session:
        exec_res = await TaskRunner.execute_job(session, claimed, worker_id)
        assert exec_res.status == ExecutionStatus.SUCCESS

    # Verify final state: lease fields cleared
    async with AsyncSessionLocal() as session:
        final_job = await session.get(Job, job_id)
        assert final_job.status == JobStatus.COMPLETED
        assert final_job.locked_by_worker_id is None
        assert final_job.lease_token is None
        assert final_job.lock_expires_at is None
        assert final_job.completed_at is not None


# =========================================================================
# TEST 2.2B — Crash Recovery: Heartbeat Stops -> Worker DEAD -> Lease Expires -> Reaper Requeues -> Worker B Completes
# =========================================================================
@pytest.mark.asyncio
async def test_worker_crash_and_lease_reaper_requeue(lease_env):
    """
    Verifies fault-tolerant recovery when heartbeat stops:
    1. Worker A claims job with a short lease
    2. Worker A crashes (stops heartbeating)
    3. Worker A's heartbeat becomes stale (>30s ago) and lease expires
    4. LeaseReaper runs:
       - Identifies Worker A as DEAD
       - Reclaims the expired job back to QUEUED (clearing Worker A's lease)
    5. Healthy Worker B claims the job and executes it to COMPLETED
    """
    queue_id = lease_env["queue_id"]
    queue_name = lease_env["queue_name"]
    worker_a_id = lease_env["worker_a_id"]
    worker_b_id = lease_env["worker_b_id"]
    now_utc = datetime.now(timezone.utc)

    # 1. Enqueue job with max_retries = 3
    async with AsyncSessionLocal() as session:
        job = Job(
            queue_id=queue_id,
            name="generate_monthly_report",
            status=JobStatus.QUEUED,
            payload={"month": "August", "year": 2026},
            max_retries=3,
            run_at=now_utc,
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    # 2. Worker A claims the job
    async with AsyncSessionLocal() as session:
        claimed_a = await AtomicClaimer.claim_next_job(
            session, worker_id=worker_a_id, assigned_queues=[queue_name]
        )
        assert claimed_a is not None
        assert claimed_a.id == job_id
        assert claimed_a.locked_by_worker_id == worker_a_id
        worker_a_lease_token = claimed_a.lease_token

    # 3. Simulate Worker A crash: heartbeat stops, timestamp becomes 45s stale, lease expires
    stale_time = now_utc - timedelta(seconds=45)
    async with AsyncSessionLocal() as session:
        # Mark Worker A heartbeat stale
        await session.execute(
            Worker.__table__.update()
            .where(Worker.worker_id == worker_a_id)
            .values(last_heartbeat_at=stale_time)
        )
        # Expire Job lease
        await session.execute(
            Job.__table__.update()
            .where(Job.id == job_id)
            .values(lock_expires_at=stale_time)
        )
        await session.commit()

    # 4. LeaseReaper sweeps the cluster
    reaper = LeaseReaper(scan_interval=1)
    async with AsyncSessionLocal() as session:
        reap_res = await reaper.reap_expired_leases(session)
        assert reap_res["dead_workers_detected"] >= 1
        assert reap_res["jobs_requeued"] >= 1

    # Verify Worker A is marked DEAD and Job is QUEUED
    async with AsyncSessionLocal() as session:
        worker_a_db = await session.scalar(
            select(Worker).where(Worker.worker_id == worker_a_id)
        )
        assert worker_a_db.status == WorkerStatus.DEAD

        requeued_job = await session.get(Job, job_id)
        assert requeued_job.status == JobStatus.QUEUED
        assert requeued_job.locked_by_worker_id is None
        assert requeued_job.lease_token is None
        assert requeued_job.lock_expires_at is None
        assert "Worker lease expired" in (requeued_job.error_message or "")

    # 5. Healthy Worker B claims and completes the requeued job
    async with AsyncSessionLocal() as session:
        claimed_b = await AtomicClaimer.claim_next_job(
            session, worker_id=worker_b_id, assigned_queues=[queue_name]
        )
        assert claimed_b is not None
        assert claimed_b.id == job_id
        assert claimed_b.locked_by_worker_id == worker_b_id
        # New lease token is distinct from crashed Worker A's token
        assert claimed_b.lease_token != worker_a_lease_token

        exec_b = await TaskRunner.execute_job(session, claimed_b, worker_b_id)
        assert exec_b.status == ExecutionStatus.SUCCESS

    # 6. Verify final state is COMPLETED
    async with AsyncSessionLocal() as session:
        final_job = await session.get(Job, job_id)
        assert final_job.status == JobStatus.COMPLETED
        assert final_job.completed_at is not None
