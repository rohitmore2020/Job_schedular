import pytest
import asyncio
import uuid
from datetime import datetime, timezone
from sqlalchemy import select

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
from worker.app.engine.daemon import WorkerDaemon
from worker.app.tasks.registry import task_registry


# Register a slow task for testing graceful draining
@task_registry.register("slow_graceful_task")
async def handle_slow_graceful_task(payload: dict):
    sleep_duration = payload.get("duration", 0.5)
    await asyncio.sleep(sleep_duration)
    return {"status": "drained_cleanly", "task_id": payload.get("task_id")}


@pytest.fixture
async def shutdown_env():
    """Sets up an isolated environment for graceful shutdown testing."""
    async with AsyncSessionLocal() as session:
        org = Organization(
            name="Shutdown Org", slug=f"shutdown-org-{uuid.uuid4().hex[:6]}"
        )
        session.add(org)
        await session.flush()

        project = Project(
            org_id=org.id,
            name="Shutdown Project",
            slug=f"shutdown-proj-{uuid.uuid4().hex[:6]}",
        )
        session.add(project)
        await session.flush()

        queue = Queue(
            project_id=project.id,
            name=f"shutdown-queue-{uuid.uuid4().hex[:6]}",
            priority=50,
            concurrency_limit=10,
            is_paused=False,
        )
        session.add(queue)
        await session.commit()
        await session.refresh(queue)

        return {
            "queue_id": queue.id,
            "queue_name": queue.name,
        }


# =========================================================================
# TEST 2.4 — Worker Graceful Shutdown Flow
# Flow:
# Worker receives SIGTERM/stop() -> Stop accepting new jobs -> Finish active jobs
# -> Heartbeat status = DRAINING -> Exit (DEAD)
# =========================================================================
@pytest.mark.asyncio
async def test_worker_graceful_shutdown_flow(shutdown_env):
    queue_id = shutdown_env["queue_id"]
    queue_name = shutdown_env["queue_name"]
    worker_id = f"worker-graceful-{uuid.uuid4().hex[:6]}"

    # 1. Enqueue 2 jobs: Job 1 (long running to be in-flight), Job 2 (queued to be rejected/not claimed)
    async with AsyncSessionLocal() as session:
        job1 = Job(
            queue_id=queue_id,
            name="slow_graceful_task",
            status=JobStatus.QUEUED,
            payload={"task_id": "job_1_inflight", "duration": 0.4},
            run_at=datetime.now(timezone.utc),
        )
        job2 = Job(
            queue_id=queue_id,
            name="slow_graceful_task",
            status=JobStatus.QUEUED,
            payload={"task_id": "job_2_pending", "duration": 0.1},
            run_at=datetime.now(timezone.utc),
        )
        session.add(job1)
        session.add(job2)
        await session.commit()
        job1_id = job1.id
        job2_id = job2.id

    # 2. Instantiate and start WorkerDaemon
    daemon = WorkerDaemon(
        worker_id=worker_id,
        concurrency=1,  # Concurrency = 1 ensures Job 1 runs while Job 2 waits
        assigned_queues=[queue_name],
        poll_interval=0.05,
    )

    worker_task = asyncio.create_task(daemon.start())

    # Wait for daemon to pick up Job 1 and start running
    await asyncio.sleep(0.15)

    # Verify Worker is registered ALIVE and Job 1 is in RUNNING state
    async with AsyncSessionLocal() as session:
        worker_record = await session.scalar(
            select(Worker).where(Worker.worker_id == worker_id)
        )
        assert worker_record is not None
        assert worker_record.status == WorkerStatus.ALIVE

        running_job = await session.get(Job, job1_id)
        assert running_job.status == JobStatus.RUNNING
        assert running_job.locked_by_worker_id == worker_id

    # 3. Trigger Graceful Shutdown (SIGTERM / stop)
    stop_task = asyncio.create_task(daemon.stop())
    await asyncio.sleep(0.01)

    # Check immediate state: Daemon is_running is False (stopped accepting new jobs)
    assert daemon.is_running is False

    # Check database: Worker status transitioned to DRAINING
    await asyncio.sleep(0.05)
    async with AsyncSessionLocal() as session:
        draining_worker = await session.scalar(
            select(Worker).where(Worker.worker_id == worker_id)
        )
        assert draining_worker.status in (WorkerStatus.DRAINING, WorkerStatus.DEAD)

    # 4. Wait for graceful stop to finish draining active in-flight task (Job 1)
    await stop_task
    await worker_task

    # 5. Assertions:
    async with AsyncSessionLocal() as session:
        # Job 1 (in-flight during shutdown) completed cleanly with 0 errors
        db_job1 = await session.get(Job, job1_id)
        assert db_job1.status == JobStatus.COMPLETED
        assert db_job1.result == {"status": "drained_cleanly", "task_id": "job_1_inflight"}
        assert db_job1.completed_at is not None

        # Job 2 was NOT claimed by draining worker and remains safely in QUEUED state
        db_job2 = await session.get(Job, job2_id)
        assert db_job2.status == JobStatus.QUEUED
        assert db_job2.locked_by_worker_id is None

        # Worker record on final exit is marked DEAD
        final_worker = await session.scalar(
            select(Worker).where(Worker.worker_id == worker_id)
        )
        assert final_worker.status == WorkerStatus.DEAD
        assert final_worker.current_active_jobs == 0
