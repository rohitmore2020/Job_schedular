import pytest
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, text
from croniter import croniter

from backend.app.core.database import AsyncSessionLocal
from backend.app.models import (
    Organization,
    Project,
    Queue,
    Job,
    JobExecution,
    JobStatus,
    ExecutionStatus,
    ScheduledJob,
    User,
    UserRole,
    Worker,
    WorkerStatus,
)
from backend.app.core.security import hash_password
from worker.app.engine.claimer import AtomicClaimer
from worker.app.engine.runner import TaskRunner
from worker.app.reaper import LeaseReaper
from worker.app.cron import CronDispatcher


@pytest.fixture
async def dist_env():
    """Sets up a clean organization, project, and queue for distributed tests."""
    async with AsyncSessionLocal() as session:
        org = Organization(name="Distributed Test Org", slug=f"dist-org-{uuid.uuid4().hex[:6]}")
        session.add(org)
        await session.flush()

        user = User(
            org_id=org.id,
            email=f"dist-{uuid.uuid4().hex[:6]}@example.com",
            hashed_password=hash_password("Password123!"),
            full_name="Distributed Tester",
            role=UserRole.ADMIN,
        )
        session.add(user)

        proj = Project(org_id=org.id, name="Dist Proj", slug=f"dist-p-{uuid.uuid4().hex[:6]}")
        session.add(proj)
        await session.flush()

        queue = Queue(
            project_id=proj.id,
            name=f"dist-q-{uuid.uuid4().hex[:6]}",
            priority=50,
            concurrency_limit=10,
            is_paused=False,
        )
        session.add(queue)
        await session.commit()
        await session.refresh(queue)
        await session.refresh(user)

        return {
            "org_id": org.id,
            "user_id": user.id,
            "project_id": proj.id,
            "queue_id": queue.id,
            "queue_name": queue.name,
        }


# =========================================================================
# TEST 1 — Two Workers, One Job (Mutual Exclusion Race)
# =========================================================================
@pytest.mark.asyncio
async def test_dist_1_two_workers_one_job_mutual_exclusion(dist_env):
    """
    Worker A ──┐
               ├── Job X
    Worker B ──┘
    Expected: Exactly one worker claims Job X with a valid lease token.
    """
    queue_id = dist_env["queue_id"]
    queue_name = dist_env["queue_name"]

    # 1. Insert single job into queue
    async with AsyncSessionLocal() as session:
        job = Job(
            queue_id=queue_id,
            name="exclusive_task",
            status=JobStatus.QUEUED,
            payload={"task": "exclusive"},
            run_at=datetime.now(timezone.utc),
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    worker_a = "worker-alpha"
    worker_b = "worker-beta"

    # 2. Both workers race concurrently to claim the single job
    async def try_claim(worker_id):
        async with AsyncSessionLocal() as session:
            return await AtomicClaimer.claim_next_job(
                session, worker_id=worker_id, assigned_queues=[queue_name]
            )

    results = await asyncio.gather(
        try_claim(worker_a),
        try_claim(worker_b),
    )

    claimed_jobs = [r for r in results if r is not None]

    # Assert mutual exclusion: Exactly 1 worker got the job
    assert len(claimed_jobs) == 1, f"Expected 1 claim, got {len(claimed_jobs)}"
    winner = claimed_jobs[0]
    assert winner.id == job_id
    assert winner.status == JobStatus.RUNNING
    assert winner.lease_token is not None
    assert winner.locked_by_worker_id in [worker_a, worker_b]

    # 3. Winning worker executes and completes the job
    async with AsyncSessionLocal() as session:
        exec_res = await TaskRunner.execute_job(session, winner, winner.locked_by_worker_id)
        assert exec_res.status == ExecutionStatus.SUCCESS

    # 4. Verify total executions in DB is exactly 1
    async with AsyncSessionLocal() as session:
        exec_count = await session.scalar(
            select(func.count(JobExecution.id)).where(JobExecution.job_id == job_id)
        )
        assert exec_count == 1

        final_job = await session.get(Job, job_id)
        assert final_job.status == JobStatus.COMPLETED


# =========================================================================
# TEST 2 — 100 Jobs, 5 Parallel Workers (Distributed Ingestion & Draining)
# =========================================================================
@pytest.mark.asyncio
async def test_dist_2_100_jobs_5_workers_no_duplicates(dist_env):
    """
    100 jobs
       ↓
    5 parallel workers
    Expected: Exactly 100 completed executions, 0 duplicate claims, 0 orphaned jobs.
    """
    queue_id = dist_env["queue_id"]
    queue_name = dist_env["queue_name"]
    total_jobs = 100

    # 1. Bulk insert 100 jobs
    async with AsyncSessionLocal() as session:
        now_utc = datetime.now(timezone.utc)
        for i in range(total_jobs):
            job = Job(
                queue_id=queue_id,
                name=f"parallel_task_{i}",
                status=JobStatus.QUEUED,
                payload={"index": i},
                run_at=now_utc,
            )
            session.add(job)
        await session.commit()

    # 2. Worker runner loop
    async def worker_loop(worker_id: str):
        processed = 0
        while True:
            async with AsyncSessionLocal() as session:
                job = await AtomicClaimer.claim_next_job(
                    session, worker_id=worker_id, assigned_queues=[queue_name]
                )
                if not job:
                    break
                exec_record = await TaskRunner.execute_job(session, job, worker_id)
                assert exec_record.status == ExecutionStatus.SUCCESS
                processed += 1
        return processed

    # 3. Launch 5 parallel workers
    workers = [f"worker-node-{i}" for i in range(5)]
    worker_tasks = [worker_loop(w) for w in workers]
    counts = await asyncio.gather(*worker_tasks)

    # 4. Assert total processed across all 5 workers equals exactly 100
    assert sum(counts) == total_jobs, f"Expected 100 jobs processed, got {sum(counts)}"

    # 5. Verify database consistency
    async with AsyncSessionLocal() as session:
        completed_count = await session.scalar(
            select(func.count(Job.id)).where(Job.queue_id == queue_id, Job.status == JobStatus.COMPLETED)
        )
        assert completed_count == total_jobs

        non_completed = await session.scalar(
            select(func.count(Job.id)).where(Job.queue_id == queue_id, Job.status != JobStatus.COMPLETED)
        )
        assert non_completed == 0

        total_executions = await session.scalar(
            select(func.count(JobExecution.id))
            .join(Job, JobExecution.job_id == Job.id)
            .where(Job.queue_id == queue_id)
        )
        assert total_executions == total_jobs


# =========================================================================
# TEST 3 — Concurrency = 3 Invariant with 5 Workers & 100 Jobs
# =========================================================================
@pytest.mark.asyncio
async def test_dist_3_queue_concurrency_invariant_3_with_5_workers(dist_env):
    """
    5 workers, 50 jobs, queue limit = 3
    Expected: At NO point in time does running count ever exceed 3.
    """
    queue_id = dist_env["queue_id"]
    queue_name = dist_env["queue_name"]
    total_jobs = 40
    concurrency_limit = 3

    # Update queue concurrency limit to 3
    async with AsyncSessionLocal() as session:
        q = await session.get(Queue, queue_id)
        q.concurrency_limit = concurrency_limit
        now_utc = datetime.now(timezone.utc)
        for i in range(total_jobs):
            job = Job(
                queue_id=queue_id,
                name=f"concurrency_task_{i}",
                status=JobStatus.QUEUED,
                payload={"index": i, "simulated_delay": 0.05},
                run_at=now_utc,
            )
            session.add(job)
        await session.commit()

    max_running_observed = 0
    monitoring = True

    # 1. Background Invariant Monitor
    async def monitor_concurrency():
        nonlocal max_running_observed
        while monitoring:
            async with AsyncSessionLocal() as session:
                running_now = await session.scalar(
                    select(func.count(Job.id)).where(
                        Job.queue_id == queue_id,
                        Job.status == JobStatus.RUNNING,
                    )
                )
                if running_now and running_now > max_running_observed:
                    max_running_observed = running_now
            await asyncio.sleep(0.005)

    # 2. Worker runner
    async def worker_loop(worker_id: str):
        while True:
            async with AsyncSessionLocal() as session:
                job = await AtomicClaimer.claim_next_job(
                    session, worker_id=worker_id, assigned_queues=[queue_name]
                )
                if not job:
                    # Check if any jobs remain queued
                    remaining = await session.scalar(
                        select(func.count(Job.id)).where(
                            Job.queue_id == queue_id, Job.status == JobStatus.QUEUED
                        )
                    )
                    if remaining == 0:
                        break
                    await asyncio.sleep(0.01)
                    continue

                # Simulate work duration to create overlapping pressure
                await asyncio.sleep(0.03)
                await TaskRunner.execute_job(session, job, worker_id)

    monitor_task = asyncio.create_task(monitor_concurrency())

    # Launch 5 workers competing against queue concurrency = 3
    workers = [f"concurrency-worker-{i}" for i in range(5)]
    await asyncio.gather(*[worker_loop(w) for w in workers])

    monitoring = False
    await monitor_task

    # Strict Invariant Assertion
    assert max_running_observed <= concurrency_limit, (
        f"Concurrency Invariant VIOLATED! Max running observed was {max_running_observed}, "
        f"limit was {concurrency_limit}"
    )

    # Verify all jobs eventually completed
    async with AsyncSessionLocal() as session:
        completed = await session.scalar(
            select(func.count(Job.id)).where(Job.queue_id == queue_id, Job.status == JobStatus.COMPLETED)
        )
        assert completed == total_jobs


# =========================================================================
# TEST 4 — Worker Crash & Fenced Lease Recovery
# =========================================================================
@pytest.mark.asyncio
async def test_dist_4_worker_crash_and_fenced_lease_recovery(dist_env):
    """
    Worker A ──> claims (Lease 1) ──> crashes / loses lease
    Reaper recovers job ──> resets to QUEUED
    Worker B ──> claims (Lease 2) ──> finishes
    Zombie Worker A wakes up ──> attempts completion with Lease 1 ──> Fenced & Rejected
    """
    queue_id = dist_env["queue_id"]
    queue_name = dist_env["queue_name"]

    # 1. Create a job
    async with AsyncSessionLocal() as session:
        job = Job(
            queue_id=queue_id,
            name="crash_resilient_task",
            status=JobStatus.QUEUED,
            payload={"data": "fencing_demo"},
            max_retries=3,
            run_at=datetime.now(timezone.utc),
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    # 2. Worker A claims the job with 2s lease timeout
    worker_a = "worker-crash-node"
    async with AsyncSessionLocal() as session:
        job_claimed_by_a = await AtomicClaimer.claim_next_job(
            session, worker_id=worker_a, assigned_queues=[queue_name], lock_timeout_seconds=1
        )
        assert job_claimed_by_a is not None
        lease_token_a = job_claimed_by_a.lease_token

    # 3. Simulate Worker A crash: simulate lease expiration
    async with AsyncSessionLocal() as session:
        expired_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        await session.execute(
            text("UPDATE jobs SET lock_expires_at = :exp WHERE id = :id"),
            {"exp": expired_time, "id": job_id},
        )
        await session.commit()

    # 4. Lease Reaper runs and recovers the orphaned job
    reaper = LeaseReaper(scan_interval=1)
    async with AsyncSessionLocal() as session:
        reap_res = await reaper.reap_expired_leases(session)
        assert reap_res["jobs_requeued"] >= 1

    # 5. Worker B claims the recovered job with new lease token
    worker_b = "worker-healthy-node"
    async with AsyncSessionLocal() as session:
        job_claimed_by_b = await AtomicClaimer.claim_next_job(
            session, worker_id=worker_b, assigned_queues=[queue_name], lock_timeout_seconds=30
        )
        assert job_claimed_by_b is not None
        assert job_claimed_by_b.id == job_id
        lease_token_b = job_claimed_by_b.lease_token
        assert lease_token_b != lease_token_a

    # 6. Zombie Worker A wakes up and attempts to finalize with stale lease_token_a
    async with AsyncSessionLocal() as session:
        zombie_exec = await TaskRunner.execute_job(session, job_claimed_by_a, worker_a)
        # Should be fenced and aborted
        assert zombie_exec.status == ExecutionStatus.KILLED
        assert "Fenced" in zombie_exec.error_message

    # 7. Worker B successfully completes the job
    async with AsyncSessionLocal() as session:
        valid_exec = await TaskRunner.execute_job(session, job_claimed_by_b, worker_b)
        assert valid_exec.status == ExecutionStatus.SUCCESS

    # 8. Verify final job state
    async with AsyncSessionLocal() as session:
        final_job = await session.get(Job, job_id)
        assert final_job.status == JobStatus.COMPLETED


# =========================================================================
# TEST 5 — Concurrent Idempotency (100 Simultaneous Requests)
# =========================================================================
@pytest.mark.asyncio
async def test_dist_5_concurrent_idempotency_100_requests(client):
    """
    100 identical simultaneous POST requests with same Idempotency-Key
    Expected: Exactly 1 Job row created in DB; all 100 HTTP responses return the same job ID.
    """
    # 1. Signup & Setup
    email = f"idemp-stress-{uuid.uuid4().hex[:6]}@example.com"
    signup_res = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Idempotency Tester",
            "organization_name": "Idempotency Corp",
        },
    )
    assert signup_res.status_code == 201
    token = signup_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Get default project
    p_res = await client.get("/api/v1/projects", headers=headers)
    project_id = p_res.json()[0]["id"]

    # Create queue
    q_res = await client.post(
        f"/api/v1/projects/{project_id}/queues",
        headers=headers,
        json={"name": "idemp-stress-queue", "priority": 50, "concurrency_limit": 10},
    )
    assert q_res.status_code == 201
    queue_id = q_res.json()["id"]

    shared_idempotency_key = f"idemp-burst-{uuid.uuid4().hex}"
    payload = {"name": "burst_job", "payload": {"amount": 500}, "idempotency_key": shared_idempotency_key}

    # 2. Fire 100 concurrent POST requests simultaneously
    async def send_post():
        return await client.post(
            f"/api/v1/queues/{queue_id}/jobs",
            headers=headers,
            json=payload,
        )

    responses = await asyncio.gather(*[send_post() for _ in range(100)])

    # 3. Assert all returned HTTP 200 or 201
    job_ids = set()
    for r in responses:
        assert r.status_code in [200, 201], f"Unexpected status {r.status_code}: {r.text}"
        job_ids.add(r.json()["id"])

    # 4. Assert ALL 100 responses pointed to the EXACT SAME single job
    assert len(job_ids) == 1, f"Expected 1 unique job ID, got {len(job_ids)}: {job_ids}"

    # 5. Verify database has exactly 1 row
    async with AsyncSessionLocal() as session:
        count = await session.scalar(
            select(func.count(Job.id)).where(
                Job.queue_id == uuid.UUID(queue_id),
                Job.idempotency_key == shared_idempotency_key,
            )
        )
        assert count == 1


# =========================================================================
# TEST 6 — Scheduler Race (Multiple Cron Dispatchers)
# =========================================================================
@pytest.mark.asyncio
async def test_dist_6_scheduler_race_multiple_cron_dispatchers(dist_env):
    """
    Scheduler A ──┐
                  ├── cron occurrence (next_run_at <= now)
    Scheduler B ──┘
    Expected: Exactly 1 child job occurrence enqueued. 0 duplicates.
    """
    project_id = dist_env["project_id"]
    queue_id = dist_env["queue_id"]
    now_utc = datetime.now(timezone.utc)
    due_time = now_utc - timedelta(seconds=15)

    # 1. Create a scheduled recurring job due right now
    async with AsyncSessionLocal() as session:
        sched = ScheduledJob(
            project_id=project_id,
            queue_id=queue_id,
            name="recurring_cleanup_cron",
            cron_expression="* * * * *",
            payload={"action": "purge_temp"},
            priority=80,
            is_active=True,
            next_run_at=due_time,
        )
        session.add(sched)
        await session.commit()
        sched_id = sched.id

    # 2. Instantiate 3 independent scheduler instances (simulating 3 HA replicas)
    sched_a = CronDispatcher(check_interval_seconds=1)
    sched_b = CronDispatcher(check_interval_seconds=1)
    sched_c = CronDispatcher(check_interval_seconds=1)

    async def run_dispatch(dispatcher):
        async with AsyncSessionLocal() as session:
            return await dispatcher.dispatch_due_schedules(session, schedule_id=sched_id)

    # 3. All 3 evaluate the due schedules concurrently
    results = await asyncio.gather(
        run_dispatch(sched_a),
        run_dispatch(sched_b),
        run_dispatch(sched_c),
    )

    # Total dispatched across all 3 should be 1
    total_dispatched = sum(results)
    assert total_dispatched == 1, f"Expected 1 cron job dispatched, got {total_dispatched}"

    # 4. Verify in DB that exactly 1 child job was created with deterministic logical key
    async with AsyncSessionLocal() as session:
        child_jobs = (
            await session.execute(
                select(Job).where(
                    Job.queue_id == queue_id,
                    Job.name == "recurring_cleanup_cron",
                )
            )
        ).scalars().all()

        assert len(child_jobs) == 1
        created_job = child_jobs[0]
        assert created_job.idempotency_key.startswith(f"cron:{sched_id}:")
        assert created_job.status == JobStatus.QUEUED
