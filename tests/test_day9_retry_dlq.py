import pytest
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from backend.app.models import (
    Organization,
    Project,
    Queue,
    Job,
    DLQEntry,
    RetryPolicy,
    JobStatus,
    ExecutionStatus,
    RetryStrategy,
)
from worker.app.engine.retry import RetryBackoffCalculator
from worker.app.engine.claimer import AtomicClaimer
from worker.app.engine.runner import TaskRunner


def test_backoff_calculator_algorithms():
    """Verify Fixed, Linear, and Exponential retry delay formulas."""
    # 1. Fixed Policy: always 10s
    fixed_policy = RetryPolicy(
        strategy=RetryStrategy.FIXED,
        initial_interval_sec=10,
        max_interval_sec=60,
        backoff_multiplier=2.0,
        jitter=False,
    )
    assert RetryBackoffCalculator.calculate_delay(1, fixed_policy) == 10.0
    assert RetryBackoffCalculator.calculate_delay(5, fixed_policy) == 10.0

    # 2. Linear Policy: initial * attempt up to max
    linear_policy = RetryPolicy(
        strategy=RetryStrategy.LINEAR,
        initial_interval_sec=5,
        max_interval_sec=15,
        backoff_multiplier=1.0,
        jitter=False,
    )
    assert RetryBackoffCalculator.calculate_delay(1, linear_policy) == 5.0
    assert RetryBackoffCalculator.calculate_delay(2, linear_policy) == 10.0
    assert RetryBackoffCalculator.calculate_delay(3, linear_policy) == 15.0
    assert RetryBackoffCalculator.calculate_delay(4, linear_policy) == 15.0  # Capped at max

    # 3. Exponential Policy (No Jitter): 2 * (2 ^ (attempt - 1))
    exp_policy = RetryPolicy(
        strategy=RetryStrategy.EXPONENTIAL,
        initial_interval_sec=2,
        max_interval_sec=100,
        backoff_multiplier=2.0,
        jitter=False,
    )
    assert RetryBackoffCalculator.calculate_delay(1, exp_policy) == 2.0   # 2 * 1
    assert RetryBackoffCalculator.calculate_delay(2, exp_policy) == 4.0   # 2 * 2
    assert RetryBackoffCalculator.calculate_delay(3, exp_policy) == 8.0   # 2 * 4
    assert RetryBackoffCalculator.calculate_delay(4, exp_policy) == 16.0  # 2 * 8


@pytest.fixture
async def retry_queue_fixture(db_session):
    org = Organization(name="DLQ Org", slug=f"dlq-org-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    proj = Project(org_id=org.id, name="DLQ Proj", slug=f"dlq-p-{uuid.uuid4().hex[:6]}")
    db_session.add(proj)
    await db_session.flush()

    queue = Queue(
        project_id=proj.id,
        name=f"dlq-queue-{uuid.uuid4().hex[:6]}",
        priority=50,
        concurrency_limit=10,
        is_paused=False,
    )
    db_session.add(queue)
    await db_session.flush()

    policy = RetryPolicy(
        queue_id=queue.id,
        strategy=RetryStrategy.FIXED,
        initial_interval_sec=3,
        max_interval_sec=10,
        backoff_multiplier=1.0,
        jitter=False,
    )
    db_session.add(policy)
    await db_session.commit()
    await db_session.refresh(queue)
    return queue


@pytest.mark.asyncio
async def test_retry_backoff_execution_schedule(db_session, retry_queue_fixture):
    """Verify failing task reschedules into future with backoff delay."""
    queue = retry_queue_fixture
    job = Job(
        queue_id=queue.id,
        name="mock_failing_task",
        status=JobStatus.QUEUED,
        payload={"error_type": "TransientNetworkError"},
        max_retries=3,
    )
    db_session.add(job)
    await db_session.commit()

    worker_id = "test-retry-worker"
    claimed = await AtomicClaimer.claim_next_job(
        db_session, worker_id, queue_id=queue.id
    )
    assert claimed is not None

    # Execute attempt 1
    now_before = datetime.now(timezone.utc)
    execution = await TaskRunner.execute_job(db_session, claimed, worker_id)
    assert execution.status == ExecutionStatus.FAILED

    await db_session.refresh(claimed)
    assert claimed.status in (JobStatus.QUEUED, JobStatus.SCHEDULED)
    assert claimed.attempt_count == 1
    # run_at should be pushed into future by fixed 3s
    assert claimed.run_at >= now_before + timedelta(seconds=2)


@pytest.mark.asyncio
async def test_dlq_escalation_and_replay_endpoint(client, db_session):
    """Verify DLQ endpoints: listing, replaying, and purging."""
    # 1. Sign up user
    email = f"dlq-user-{uuid.uuid4().hex[:6]}@test.com"
    signup_res = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": "DLQ User", "organization_name": "DLQ Co"},
    )
    token = signup_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Get default queue
    proj_res = await client.get("/api/v1/projects", headers=headers)
    project_id = proj_res.json()[0]["id"]
    q_res = await client.get(f"/api/v1/projects/{project_id}/queues", headers=headers)
    queue_data = q_res.json()[0]
    queue_id = uuid.UUID(queue_data["id"])

    # 3. Create a failing job with max_retries = 1
    job_res = await client.post(
        f"/api/v1/queues/{queue_id}/jobs",
        headers=headers,
        json={"name": "mock_failing_task", "payload": {"error_type": "FatalError"}, "max_retries": 1},
    )
    job_id = job_res.json()["id"]

    # 4. Trigger worker execution using NullPool db_session
    claimed = await AtomicClaimer.claim_next_job(
        db_session, "worker-dlq-test", queue_id=queue_id
    )
    assert claimed is not None
    await TaskRunner.execute_job(db_session, claimed, "worker-dlq-test")

    # 5. Query DLQ list
    dlq_list_res = await client.get(f"/api/v1/queues/{queue_id}/dlq", headers=headers)
    assert dlq_list_res.status_code == 200
    dlq_data = dlq_list_res.json()
    assert dlq_data["total"] >= 1
    dlq_entry_id = dlq_data["items"][0]["id"]

    # 6. Replay single DLQ entry
    replay_res = await client.post(f"/api/v1/dlq/{dlq_entry_id}/replay", headers=headers)
    assert replay_res.status_code == 200
    assert replay_res.json()["replayed_count"] == 1

    # 7. Verify Job is back in queued status
    job_detail = await client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert job_detail.json()["status"] == "queued"

    # 8. Replay all endpoint
    replay_all_res = await client.post(f"/api/v1/queues/{queue_id}/dlq/replay-all", headers=headers)
    assert replay_all_res.status_code == 200

    # 9. Purge DLQ entry
    purge_res = await client.delete(f"/api/v1/dlq/{dlq_entry_id}", headers=headers)
    assert purge_res.status_code == 200
    assert purge_res.json()["message"] == "DLQ entry permanently purged"
