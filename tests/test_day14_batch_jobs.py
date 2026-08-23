import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, func

from backend.app.models import (
    Organization,
    Project,
    Queue,
    Job,
    JobBatch,
    JobStatus,
    BatchStatus,
)
from backend.app.services.batch_service import BatchService
from backend.app.schemas.batch import BatchCreate
from backend.app.schemas.job import JobCreate
from worker.app.engine.daemon import WorkerDaemon
from worker.app.tasks.registry import task_registry


@pytest.fixture
async def queue_fixture(db_session):
    org = Organization(name="Batch Org", slug=f"batch-org-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    proj = Project(org_id=org.id, name="Batch Proj", slug=f"b-proj-{uuid.uuid4().hex[:6]}")
    db_session.add(proj)
    await db_session.flush()

    queue = Queue(
        project_id=proj.id,
        name=f"batch-queue-{uuid.uuid4().hex[:6]}",
        priority=50,
        concurrency_limit=10,
        is_paused=False,
    )
    db_session.add(queue)
    await db_session.commit()
    await db_session.refresh(queue)
    return queue


@pytest.mark.asyncio
async def test_batch_creation_and_child_jobs_enqueued(client):
    """Verify creating a batch of N jobs atomically via REST API."""
    # 1. Sign up user
    email = f"batch-user-{uuid.uuid4().hex[:6]}@test.com"
    signup_res = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": "Batch User", "organization_name": "Batch Co"},
    )
    token = signup_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Get default queue
    proj_res = await client.get("/api/v1/projects", headers=headers)
    project_id = proj_res.json()[0]["id"]
    q_res = await client.get(f"/api/v1/projects/{project_id}/queues", headers=headers)
    queue_id = q_res.json()[0]["id"]

    # 3. Create batch of 5 jobs
    batch_payload = {
        "name": "Invoice Generation Batch #102",
        "description": "Monthly subscription billing invoices",
        "jobs": [
            {"name": "send_email", "payload": {"invoice_id": i, "email": f"cust{i}@test.com"}, "priority": 50}
            for i in range(1, 6)
        ],
    }
    create_res = await client.post(
        f"/api/v1/queues/{queue_id}/batches",
        headers=headers,
        json=batch_payload,
    )
    assert create_res.status_code == 201
    batch_data = create_res.json()
    batch_id = batch_data["id"]

    assert batch_data["name"] == "Invoice Generation Batch #102"
    assert batch_data["status"] == "processing"
    assert batch_data["total_jobs"] == 5
    assert batch_data["completed_jobs"] == 0
    assert batch_data["failed_jobs"] == 0
    assert batch_data["pending_jobs"] == 5
    assert batch_data["progress_percent"] == 0.0
    assert len(batch_data["jobs"]) == 5

    # 4. Fetch batch details via GET /batches/{id}
    get_res = await client.get(f"/api/v1/batches/{batch_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == batch_id
    assert get_res.json()["total_jobs"] == 5

    # 5. Fetch batch child jobs via GET /batches/{id}/jobs
    jobs_res = await client.get(f"/api/v1/batches/{batch_id}/jobs", headers=headers)
    assert jobs_res.status_code == 200
    assert jobs_res.json()["total"] == 5
    for item in jobs_res.json()["items"]:
        assert item["batch_id"] == batch_id
        assert item["status"] == "queued"


@pytest.mark.asyncio
async def test_batch_execution_and_live_progress_tracking(client, db_session, queue_fixture):
    """Verify live progress percentage and status transition as workers process batch jobs."""
    queue = queue_fixture

    # Register mock test handlers
    @task_registry.register("batch_success_task")
    async def batch_success_task(payload, ctx):
        return {"processed": True, "item": payload.get("item")}

    @task_registry.register("batch_failing_task")
    async def batch_failing_task(payload, ctx):
        raise ValueError("Simulated permanent worker failure")

    # 1. Sign up user
    email = f"batch-prog-{uuid.uuid4().hex[:6]}@test.com"
    signup_res = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": "Progress User", "organization_name": "Progress Co"},
    )
    token = signup_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create isolated queue for test
    proj_res = await client.get("/api/v1/projects", headers=headers)
    project_id = proj_res.json()[0]["id"]
    queue_create_res = await client.post(
        f"/api/v1/projects/{project_id}/queues",
        headers=headers,
        json={"name": f"batch-q-{uuid.uuid4().hex[:6]}", "priority": 100, "concurrency_limit": 10},
    )
    assert queue_create_res.status_code == 201
    user_queue_data = queue_create_res.json()
    user_queue_id = user_queue_data["id"]
    user_queue_name = user_queue_data["name"]

    # 3. Create batch with 3 successful jobs and 1 failing job (max_retries=0 for immediate DLQ)
    jobs_payload = [
        {"name": "batch_success_task", "payload": {"item": 1}, "priority": 50, "max_retries": 1},
        {"name": "batch_success_task", "payload": {"item": 2}, "priority": 50, "max_retries": 1},
        {"name": "batch_success_task", "payload": {"item": 3}, "priority": 50, "max_retries": 1},
        {"name": "batch_failing_task", "payload": {"item": 4}, "priority": 50, "max_retries": 0},
    ]
    batch_res = await client.post(
        f"/api/v1/queues/{user_queue_id}/batches",
        headers=headers,
        json={"name": "Nightly Video Transcoding", "jobs": jobs_payload},
    )
    assert batch_res.status_code == 201
    batch_id = batch_res.json()["id"]

    # 4. Run worker daemon to process all 4 jobs strictly from this queue
    daemon = WorkerDaemon(
        worker_id=f"worker-batch-{uuid.uuid4().hex[:6]}",
        concurrency=4,
        assigned_queues=[user_queue_name],
    )
    for _ in range(4):
        await daemon.run_once()

    # 5. Query batch detail to verify live progress tracking
    detail_res = await client.get(f"/api/v1/batches/{batch_id}", headers=headers)
    assert detail_res.status_code == 200
    data = detail_res.json()

    assert data["total_jobs"] == 4
    assert data["completed_jobs"] == 3
    assert data["failed_jobs"] == 1
    assert data["pending_jobs"] == 0
    assert data["progress_percent"] == 100.0
    assert data["status"] == "partially_failed"
    assert data["completed_at"] is not None


@pytest.mark.asyncio
async def test_batch_cancel_and_retry_lifecycle(client):
    """Verify cancelling all remaining jobs in a batch and retrying failed/cancelled ones."""
    # 1. Sign up user
    email = f"batch-lifecycle-{uuid.uuid4().hex[:6]}@test.com"
    signup_res = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": "Lifecycle User", "organization_name": "Life Co"},
    )
    token = signup_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Get user queue
    proj_res = await client.get("/api/v1/projects", headers=headers)
    project_id = proj_res.json()[0]["id"]
    q_res = await client.get(f"/api/v1/projects/{project_id}/queues", headers=headers)
    queue_id = q_res.json()[0]["id"]

    # 3. Create batch of 3 jobs
    batch_res = await client.post(
        f"/api/v1/queues/{queue_id}/batches",
        headers=headers,
        json={
            "name": "Export Catalog Batch",
            "jobs": [
                {"name": "send_email", "payload": {"item": i}} for i in range(3)
            ],
        },
    )
    assert batch_res.status_code == 201
    batch_id = batch_res.json()["id"]

    # 4. Cancel the batch
    cancel_res = await client.post(f"/api/v1/batches/{batch_id}/cancel", headers=headers)
    assert cancel_res.status_code == 200
    cancel_data = cancel_res.json()
    assert cancel_data["status"] == "cancelled"
    assert cancel_data["cancelled_jobs"] == 3

    # Verify child jobs are CANCELLED
    jobs_res = await client.get(f"/api/v1/batches/{batch_id}/jobs", headers=headers)
    for j in jobs_res.json()["items"]:
        assert j["status"] == "cancelled"

    # 5. Retry the batch
    retry_res = await client.post(f"/api/v1/batches/{batch_id}/retry", headers=headers)
    assert retry_res.status_code == 200
    retry_data = retry_res.json()
    assert retry_data["status"] == "processing"

    # Verify child jobs are reset to QUEUED
    jobs_res = await client.get(f"/api/v1/batches/{batch_id}/jobs", headers=headers)
    for j in jobs_res.json()["items"]:
        assert j["status"] == "queued"


@pytest.mark.asyncio
async def test_batch_listing_and_pagination(client):
    """Verify listing batches with pagination and filtering."""
    # 1. Sign up user
    email = f"batch-list-{uuid.uuid4().hex[:6]}@test.com"
    signup_res = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": "List User", "organization_name": "List Co"},
    )
    token = signup_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Get user queue
    proj_res = await client.get("/api/v1/projects", headers=headers)
    project_id = proj_res.json()[0]["id"]
    q_res = await client.get(f"/api/v1/projects/{project_id}/queues", headers=headers)
    queue_id = q_res.json()[0]["id"]

    # 3. Create 3 batches
    for i in range(1, 4):
        await client.post(
            f"/api/v1/queues/{queue_id}/batches",
            headers=headers,
            json={"name": f"Batch #{i}", "jobs": [{"name": "task", "payload": {"i": i}}]},
        )

    # 4. List batches
    list_res = await client.get("/api/v1/batches?page=1&page_size=2", headers=headers)
    assert list_res.status_code == 200
    data = list_res.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["total_pages"] == 2

