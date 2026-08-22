import pytest
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.models import (
    Organization,
    Project,
    Queue,
    Job,
    JobStatus,
    DLQEntry,
)
from backend.app.schemas.job import JobCreate
from backend.app.services.job_service import JobService
from worker.app.engine.runner import TaskRunner
from worker.app.engine.rate_limiter import TokenBucket, QueueRateLimiter
from worker.app.engine.ai_diagnostics import AIDiagnosticEngine


@pytest.fixture
async def setup_dag_fixtures(db_session):
    org = Organization(name="DAG Org", slug=f"dag-org-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    proj = Project(org_id=org.id, name="DAG Proj", slug=f"d-proj-{uuid.uuid4().hex[:6]}")
    db_session.add(proj)
    await db_session.flush()

    queue = Queue(
        project_id=proj.id,
        name=f"dag-queue-{uuid.uuid4().hex[:6]}",
        priority=50,
        concurrency_limit=10,
        rate_limit_rps=10,
        is_paused=False,
    )
    db_session.add(queue)
    await db_session.commit()
    await db_session.refresh(queue)
    return org, proj, queue


@pytest.mark.asyncio
async def test_dag_workflow_dependency_success_chain(db_session, setup_dag_fixtures):
    """Verify child job waits for parent job and automatically unlocks upon parent completion."""
    org, proj, queue = setup_dag_fixtures

    # 1. Create Parent Job
    parent_job = Job(
        queue_id=queue.id,
        name="send_email",
        status=JobStatus.QUEUED,
        priority=50,
        payload={"email": "parent@dag.com"},
    )
    db_session.add(parent_job)
    await db_session.commit()
    await db_session.refresh(parent_job)

    # 2. Create Child Job with parent_job_id
    child_job = Job(
        queue_id=queue.id,
        name="calculate_report",
        status=JobStatus.SCHEDULED,
        priority=40,
        payload={"report_type": "downstream_summary"},
        parent_job_id=parent_job.id,
    )
    db_session.add(child_job)
    await db_session.commit()
    await db_session.refresh(child_job)

    assert child_job.status == JobStatus.SCHEDULED

    # 3. Execute Parent Job
    parent_job.status = JobStatus.RUNNING
    parent_job.locked_by_worker_id = "worker-dag-test"
    parent_job.attempt_count = 1
    await db_session.commit()

    await TaskRunner.execute_job(db_session, parent_job.id, "worker-dag-test")

    # 4. Assert Parent is Completed and Child is Unlocked to QUEUED
    stmt = select(Job).where(Job.id == parent_job.id).execution_options(populate_existing=True)
    res = await db_session.execute(stmt)
    refreshed_parent = res.scalar_one()
    assert refreshed_parent.status == JobStatus.COMPLETED

    child_stmt = select(Job).where(Job.id == child_job.id).execution_options(populate_existing=True)
    child_res = await db_session.execute(child_stmt)
    refreshed_child = child_res.scalar_one()

    assert refreshed_child.status == JobStatus.QUEUED
    assert refreshed_child.run_at <= datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_dag_workflow_cascade_cancellation_on_dlq(db_session, setup_dag_fixtures):
    """Verify child job is cancelled if parent job exhausts retries and moves to DLQ."""
    org, proj, queue = setup_dag_fixtures

    # 1. Create Failing Parent Job (max_retries = 1)
    parent_job = Job(
        queue_id=queue.id,
        name="mock_failing_task",
        status=JobStatus.RUNNING,
        priority=50,
        payload={"error_type": "DatabaseTimeout"},
        attempt_count=1,
        max_retries=1,
        locked_by_worker_id="worker-fail-test",
    )
    db_session.add(parent_job)
    await db_session.commit()
    await db_session.refresh(parent_job)

    # 2. Create Dependent Child Job
    child_job = Job(
        queue_id=queue.id,
        name="calculate_report",
        status=JobStatus.SCHEDULED,
        priority=30,
        parent_job_id=parent_job.id,
    )
    db_session.add(child_job)
    await db_session.commit()

    # 3. Execute failing parent
    await TaskRunner.execute_job(db_session, parent_job.id, "worker-fail-test")

    # 4. Assert Parent is in DLQ and Child is CANCELLED
    stmt = select(Job).where(Job.id == parent_job.id).execution_options(populate_existing=True)
    res = await db_session.execute(stmt)
    refreshed_parent = res.scalar_one()
    assert refreshed_parent.status == JobStatus.DEAD_LETTER

    child_stmt = select(Job).where(Job.id == child_job.id).execution_options(populate_existing=True)
    child_res = await db_session.execute(child_stmt)
    refreshed_child = child_res.scalar_one()

    assert refreshed_child.status == JobStatus.CANCELLED
    assert "Parent DAG Job" in refreshed_child.error_message


@pytest.mark.asyncio
async def test_token_bucket_rate_limiter():
    """Verify TokenBucket enforces rate limit and replenishes tokens over time."""
    # 2 requests per second
    bucket = TokenBucket(rate_limit_rps=2.0)

    # First 2 claims should succeed immediately
    assert await bucket.consume(1.0) == True
    assert await bucket.consume(1.0) == True

    # 3rd claim without delay should fail
    assert await bucket.consume(1.0) == False

    # Wait 0.6 seconds (should replenish ~1.2 tokens)
    await asyncio.sleep(0.6)
    assert await bucket.consume(1.0) == True


def test_ai_failure_diagnostic_engine():
    """Verify AIDiagnosticEngine categorizes errors and provides actionable recommendations."""
    # Test 1: OOM Error
    oom_summary = AIDiagnosticEngine.analyze_failure(
        task_name="render_video",
        error_message="Process killed by signal 9 (SIGKILL): Out of memory",
        stack_trace="MemoryError: unable to allocate array",
    )
    assert "Memory Exhaustion (OOM)" in oom_summary
    assert "Increase worker container memory" in oom_summary

    # Test 2: Network Timeout
    timeout_summary = AIDiagnosticEngine.analyze_failure(
        task_name="send_webhook",
        error_message="HTTP 504 Gateway Timeout",
        stack_trace="ConnectError: connection timed out after 30000ms",
    )
    assert "Gateway Timeout" in timeout_summary
    assert "Replay Safe" in timeout_summary

    # Test 3: Schema Validation
    schema_summary = AIDiagnosticEngine.analyze_failure(
        task_name="process_order",
        error_message="KeyError: 'customer_id'",
        stack_trace="ValidationError: missing required field 'customer_id'",
    )
    assert "Validation Failure" in schema_summary
    assert "Replay Safe]: No" in schema_summary


@pytest.mark.asyncio
async def test_at_least_once_execution_context_and_side_effect_idempotency(db_session, setup_dag_fixtures):
    """
    CRITICAL AT-LEAST-ONCE IDEMPOTENCY TEST:
    Verifies that:
    1. Every execution has a unique execution_id and exposes attempt_number via ExecutionContext.
    2. External side-effects (e.g. Stripe charge) wrapped with execute_idempotent_operation
       are executed EXACTLY ONCE across multiple at-least-once retry attempts.
    """
    from backend.app.models import JobExecution
    from backend.app.models.idempotency import IdempotencyRecord
    from worker.app.engine.context import ExecutionContext
    from worker.app.tasks.registry import task_registry

    org, proj, queue = setup_dag_fixtures

    external_call_counter = 0

    @task_registry.register("test_external_charge_task")
    async def handle_test_charge(payload: dict, ctx: ExecutionContext):
        nonlocal external_call_counter

        async def charge_gateway():
            nonlocal external_call_counter
            external_call_counter += 1
            return {"charge_id": "ch_test_999", "status": "succeeded", "call_count": external_call_counter}

        # Guaranteed idempotent operation
        result = await ctx.execute_idempotent_operation("payment_gateway_charge", charge_gateway)
        return result

    # 1. Create Job with max_retries = 2
    job = Job(
        queue_id=queue.id,
        name="test_external_charge_task",
        status=JobStatus.QUEUED,
        payload={"order_id": "ord_888"},
        max_retries=2,
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    # 2. Worker 1 claims job (Attempt 1)
    job.status = JobStatus.RUNNING
    job.locked_by_worker_id = "worker-node-1"
    job.attempt_count = 1
    await db_session.commit()

    exec_1 = await TaskRunner.execute_job(db_session, job.id, "worker-node-1")
    assert exec_1.attempt_number == 1
    assert exec_1.id is not None
    assert external_call_counter == 1

    # Verify idempotency record persisted in DB
    key = f"job:{job.id}:op:payment_gateway_charge"
    rec_res = await db_session.execute(select(IdempotencyRecord).where(IdempotencyRecord.key == key))
    rec = rec_res.scalar_one_or_none()
    assert rec is not None
    assert rec.response_payload["charge_id"] == "ch_test_999"

    # 3. Simulate Worker 1 crashing before acknowledging DB completion:
    # Job lease expires, reaper resets to QUEUED, Worker 2 claims for Attempt 2
    job.status = JobStatus.RUNNING
    job.locked_by_worker_id = "worker-node-2"
    job.attempt_count = 2
    await db_session.commit()

    exec_2 = await TaskRunner.execute_job(db_session, job.id, "worker-node-2")
    assert exec_2.attempt_number == 2
    assert exec_2.id != exec_1.id  # New unique execution_id

    # CRITICAL: External payment gateway was NOT called a second time!
    assert external_call_counter == 1
    assert exec_2.status.value == "success"

