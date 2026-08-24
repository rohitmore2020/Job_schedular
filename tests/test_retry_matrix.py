import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy import select

from backend.app.core.database import AsyncSessionLocal
from backend.app.models import (
    Organization,
    Project,
    Queue,
    Job,
    RetryPolicy,
    DLQEntry,
    JobStatus,
    RetryStrategy,
    ExecutionStatus,
)
from worker.app.engine.retry import RetryBackoffCalculator
from worker.app.engine.runner import TaskRunner
from worker.app.tasks.registry import task_registry


# Register a deliberately failing task for retry lifecycle testing
@task_registry.register("failing_retry_matrix_task")
async def handle_failing_retry_matrix_task(payload: dict):
    raise RuntimeError("Simulated transient downstream error for retry testing")


# =========================================================================
# TEST 2.5A — Mathematical Test Matrix Verification (Fixed, Linear, Exponential)
# =========================================================================
@pytest.mark.parametrize(
    "strategy,initial,mult,attempt,expected_delay",
    [
        # Fixed: initial = 10s (X)
        (RetryStrategy.FIXED, 10, 2.0, 1, 10.0),      # Attempt 1 -> X
        (RetryStrategy.FIXED, 10, 2.0, 2, 10.0),      # Attempt 2 -> X
        (RetryStrategy.FIXED, 10, 2.0, 3, 10.0),      # Attempt 3 -> X
        # Linear: initial = 10s (X)
        (RetryStrategy.LINEAR, 10, 2.0, 1, 10.0),     # Attempt 1 -> X
        (RetryStrategy.LINEAR, 10, 2.0, 2, 20.0),     # Attempt 2 -> 2X
        (RetryStrategy.LINEAR, 10, 2.0, 3, 30.0),     # Attempt 3 -> 3X
        # Exponential: initial = 10s (X), mult = 2.0
        (RetryStrategy.EXPONENTIAL, 10, 2.0, 1, 10.0), # Attempt 1 -> X (10 * 2^0)
        (RetryStrategy.EXPONENTIAL, 10, 2.0, 2, 20.0), # Attempt 2 -> 2X (10 * 2^1)
        (RetryStrategy.EXPONENTIAL, 10, 2.0, 3, 40.0), # Attempt 3 -> 4X (10 * 2^2)
        (RetryStrategy.EXPONENTIAL, 10, 2.0, 4, 80.0), # Attempt 4 -> 8X (10 * 2^3)
    ],
)
def test_retry_strategy_matrix(strategy, initial, mult, attempt, expected_delay):
    """
    Verifies exact mathematical backoff matrix without jitter:
    - Fixed: Attempt 1 = X, Attempt 2 = X
    - Linear: Attempt 1 = X, Attempt 2 = 2X
    - Exponential: Attempt 1 = X, Attempt 2 = 2X, Attempt 3 = 4X
    """
    policy = RetryPolicy(
        strategy=strategy,
        initial_interval_sec=initial,
        max_interval_sec=3600,
        backoff_multiplier=mult,
        jitter=False,
    )
    delay = RetryBackoffCalculator.calculate_delay(
        attempt_number=attempt, policy=policy, deterministic=True
    )
    assert delay == expected_delay


# =========================================================================
# TEST 2.5B — Max Delay Ceiling Enforcement
# =========================================================================
def test_max_delay_capping():
    """
    Verifies that backoff delay never exceeds `max_interval_sec`.
    """
    policy = RetryPolicy(
        strategy=RetryStrategy.EXPONENTIAL,
        initial_interval_sec=10,
        max_interval_sec=35,  # Cap at 35 seconds
        backoff_multiplier=2.0,
        jitter=False,
    )

    # Attempt 1 -> 10s (below cap)
    assert RetryBackoffCalculator.calculate_delay(1, policy, deterministic=True) == 10.0
    # Attempt 2 -> 20s (below cap)
    assert RetryBackoffCalculator.calculate_delay(2, policy, deterministic=True) == 20.0
    # Attempt 3 -> 40s raw -> Capped at 35s
    assert RetryBackoffCalculator.calculate_delay(3, policy, deterministic=True) == 35.0
    # Attempt 4 -> 80s raw -> Capped at 35s
    assert RetryBackoffCalculator.calculate_delay(4, policy, deterministic=True) == 35.0


# =========================================================================
# TEST 2.5C — Jitter Anti-Thundering-Herd Randomization
# =========================================================================
def test_jitter_randomization_bounds():
    """
    Verifies Full Jitter bounds: Delay is randomized within [0.5 * raw_delay, raw_delay].
    """
    policy = RetryPolicy(
        strategy=RetryStrategy.EXPONENTIAL,
        initial_interval_sec=20,
        max_interval_sec=3600,
        backoff_multiplier=2.0,
        jitter=True,
    )

    # Attempt 2 -> raw delay = 40.0s -> Jittered delay must be in [20.0s, 40.0s]
    samples = [
        RetryBackoffCalculator.calculate_delay(2, policy, deterministic=False)
        for _ in range(50)
    ]

    for d in samples:
        assert 20.0 <= d <= 40.0

    # Ensure distribution is random (not all identical values)
    assert len(set(samples)) > 10, "Jitter should produce non-deterministic random distributions"


# =========================================================================
# TEST 2.5D — Max Retries & DLQ Escalation End-to-End Flow
# =========================================================================
@pytest.mark.asyncio
async def test_max_retries_exhaustion_and_dlq_escalation():
    """
    Verifies that when task failures exceed `max_retries`, the job transitions
    to `DEAD_LETTER` status and writes an audit record to `dead_letter_queue`.
    """
    async with AsyncSessionLocal() as session:
        org = Organization(name="Retry Org", slug=f"retry-org-{uuid.uuid4().hex[:6]}")
        session.add(org)
        await session.flush()

        project = Project(
            org_id=org.id, name="Retry Proj", slug=f"retry-proj-{uuid.uuid4().hex[:6]}"
        )
        session.add(project)
        await session.flush()

        queue = Queue(
            project_id=project.id,
            name=f"retry-matrix-queue-{uuid.uuid4().hex[:6]}",
            priority=50,
            concurrency_limit=10,
            is_paused=False,
        )
        session.add(queue)
        await session.flush()

        # Retry policy with Linear strategy
        policy = RetryPolicy(
            queue_id=queue.id,
            strategy=RetryStrategy.LINEAR,
            initial_interval_sec=2,
            max_interval_sec=60,
            backoff_multiplier=1.0,
            jitter=False,
        )
        session.add(policy)
        await session.flush()

        queue.retry_policy_id = policy.id

        # Job with max_retries = 2
        job = Job(
            queue_id=queue.id,
            name="failing_retry_matrix_task",
            status=JobStatus.RUNNING,
            payload={"action": "test_failure"},
            max_retries=2,
            attempt_count=1,
            lease_token=uuid.uuid4(),
            run_at=datetime.now(timezone.utc),
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    # Attempt 1: Fails -> attempt_count (1) < max_retries (2) -> Requeued with backoff
    async with AsyncSessionLocal() as session:
        j1 = await session.get(Job, job_id)
        exec1 = await TaskRunner.execute_job(session, j1, "worker-retry-1")
        assert exec1.status == ExecutionStatus.FAILED

        # Verify job is scheduled for retry
        requeued_j1 = await session.get(Job, job_id)
        assert requeued_j1.status == JobStatus.SCHEDULED
        assert requeued_j1.run_at > datetime.now(timezone.utc)

    # Attempt 2: Fails -> attempt_count (2) == max_retries (2) -> Escalated to DEAD_LETTER
    async with AsyncSessionLocal() as session:
        j2 = await session.get(Job, job_id)
        j2.status = JobStatus.RUNNING
        j2.attempt_count = 2
        j2.lease_token = uuid.uuid4()
        await session.commit()

        exec2 = await TaskRunner.execute_job(session, j2, "worker-retry-1")
        assert exec2.status == ExecutionStatus.FAILED

        # Verify job escalated to DEAD_LETTER
        dead_job = await session.get(Job, job_id)
        assert dead_job.status == JobStatus.DEAD_LETTER

        # Verify entry created in DLQ
        dlq_entry = await session.scalar(
            select(DLQEntry).where(DLQEntry.job_id == job_id)
        )
        assert dlq_entry is not None
        assert dlq_entry.total_attempts >= 2
        assert "Simulated transient downstream error" in (dlq_entry.last_error or "")
