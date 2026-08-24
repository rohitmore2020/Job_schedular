import pytest
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from backend.app.core.database import AsyncSessionLocal
from backend.app.models import (
    Organization,
    Project,
    Queue,
    Job,
    Worker,
    JobExecution,
    JobStatus,
    WorkerStatus,
    ExecutionStatus,
)
from worker.app.engine.claimer import AtomicClaimer
from worker.app.engine.runner import TaskRunner
from worker.app.reaper import LeaseReaper


@pytest.fixture
async def zombie_test_env():
    """Sets up an isolated environment for zombie worker split-brain testing."""
    async with AsyncSessionLocal() as session:
        org = Organization(
            name="Zombie Defense Org", slug=f"zombie-org-{uuid.uuid4().hex[:6]}"
        )
        session.add(org)
        await session.flush()

        project = Project(
            org_id=org.id,
            name="Zombie Defense Project",
            slug=f"zombie-proj-{uuid.uuid4().hex[:6]}",
        )
        session.add(project)
        await session.flush()

        queue = Queue(
            project_id=project.id,
            name=f"zombie-queue-{uuid.uuid4().hex[:6]}",
            priority=50,
            concurrency_limit=10,
            is_paused=False,
        )
        session.add(queue)
        await session.flush()

        worker_a = Worker(
            worker_id=f"worker-node-A-{uuid.uuid4().hex[:6]}",
            hostname="worker-node-a.dc1.internal",
            pid=2001,
            status=WorkerStatus.ALIVE,
            current_active_jobs=0,
            assigned_queues=[queue.name],
            last_heartbeat_at=datetime.now(timezone.utc),
        )
        worker_b = Worker(
            worker_id=f"worker-node-B-{uuid.uuid4().hex[:6]}",
            hostname="worker-node-b.dc1.internal",
            pid=2002,
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
# TEST 2.3 — Zombie Worker Protection via Lease Fencing Tokens
# Flow:
# Worker A claims Job X -> Worker A becomes unhealthy -> Worker B reclaims Job X
# -> Worker B finishes SUCCESS -> Zombie Worker A attempts completion -> Worker A REJECTED
# =========================================================================
@pytest.mark.asyncio
async def test_zombie_worker_rejection_and_healthy_worker_success(zombie_test_env):
    queue_id = zombie_test_env["queue_id"]
    queue_name = zombie_test_env["queue_name"]
    worker_a_id = zombie_test_env["worker_a_id"]
    worker_b_id = zombie_test_env["worker_b_id"]
    now_utc = datetime.now(timezone.utc)

    # 1. Enqueue Job X
    async with AsyncSessionLocal() as session:
        job = Job(
            queue_id=queue_id,
            name="send_payment_webhook",
            status=JobStatus.QUEUED,
            payload={"transaction_id": "tx_99812", "amount": 2500},
            max_retries=3,
            run_at=now_utc,
        )
        session.add(job)
        await session.commit()
        job_x_id = job.id

    # 2. Worker A claims Job X (stamping Lease Token A)
    async with AsyncSessionLocal() as session:
        claimed_by_a = await AtomicClaimer.claim_next_job(
            session, worker_id=worker_a_id, assigned_queues=[queue_name]
        )
        assert claimed_by_a is not None
        assert claimed_by_a.id == job_x_id
        assert claimed_by_a.locked_by_worker_id == worker_a_id
        assert claimed_by_a.status == JobStatus.RUNNING
        lease_token_a = claimed_by_a.lease_token
        assert lease_token_a is not None

    # 3. Worker A becomes unhealthy (simulating deep GC pause / network partition / freeze)
    # The heartbeat stops and lease expires in database
    stale_time = now_utc - timedelta(seconds=60)
    async with AsyncSessionLocal() as session:
        await session.execute(
            Worker.__table__.update()
            .where(Worker.worker_id == worker_a_id)
            .values(last_heartbeat_at=stale_time)
        )
        await session.execute(
            Job.__table__.update()
            .where(Job.id == job_x_id)
            .values(lock_expires_at=stale_time)
        )
        await session.commit()

    # 4. LeaseReaper runs: Detects Worker A as DEAD and requeues Job X
    reaper = LeaseReaper(scan_interval=1)
    async with AsyncSessionLocal() as session:
        reap_res = await reaper.reap_expired_leases(session)
        assert reap_res["dead_workers_detected"] >= 1
        assert reap_res["jobs_requeued"] >= 1

    # 5. Healthy Worker B reclaims Job X (stamping fresh Lease Token B)
    async with AsyncSessionLocal() as session:
        claimed_by_b = await AtomicClaimer.claim_next_job(
            session, worker_id=worker_b_id, assigned_queues=[queue_name]
        )
        assert claimed_by_b is not None
        assert claimed_by_b.id == job_x_id
        assert claimed_by_b.locked_by_worker_id == worker_b_id
        lease_token_b = claimed_by_b.lease_token
        assert lease_token_b is not None
        assert lease_token_b != lease_token_a, "Worker B must receive a new distinct lease token"

        # Worker B executes and completes Job X
        exec_b = await TaskRunner.execute_job(session, claimed_by_b, worker_b_id)
        assert exec_b.status == ExecutionStatus.SUCCESS

    # Verify Job X is in COMPLETED state under Worker B's execution
    async with AsyncSessionLocal() as session:
        db_job = await session.get(Job, job_x_id)
        assert db_job.status == JobStatus.COMPLETED

    # 6. Zombie Worker A wakes up from freeze and attempts to complete Job X with stale Lease Token A
    async with AsyncSessionLocal() as session:
        # Worker A attempts finalization with its expired claim context
        exec_a = await TaskRunner.execute_job(session, claimed_by_a, worker_a_id)

        # Worker A MUST BE REJECTED by fencing token check
        assert exec_a.status == ExecutionStatus.KILLED
        assert "Fenced: Worker lease expired" in (exec_a.error_message or "")

    # 7. Final Verification:
    # - Job X remains COMPLETED (Worker A did not overwrite or corrupt state)
    # - Database records 2 executions: Worker B (SUCCESS), Worker A (KILLED)
    async with AsyncSessionLocal() as session:
        final_job = await session.get(Job, job_x_id)
        assert final_job.status == JobStatus.COMPLETED

        execs_res = await session.execute(
            select(JobExecution).where(JobExecution.job_id == job_x_id).order_by(JobExecution.started_at.asc())
        )
        exec_rows = execs_res.scalars().all()
        assert len(exec_rows) == 2

        worker_b_rec = [e for e in exec_rows if e.worker_id == worker_b_id][0]
        worker_a_rec = [e for e in exec_rows if e.worker_id == worker_a_id][0]

        assert worker_b_rec.status == ExecutionStatus.SUCCESS
        assert worker_a_rec.status == ExecutionStatus.KILLED
