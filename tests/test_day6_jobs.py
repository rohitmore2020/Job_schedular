import pytest
import uuid


@pytest.fixture
async def auth_setup(client):
    """Create a user and return auth headers and the default queue ID."""
    email = f"jobtester-{uuid.uuid4().hex[:6]}@test.com"
    payload = {
        "email": email,
        "password": "Password123!",
        "full_name": "Job Tester",
        "organization_name": "Job Systems",
    }
    signup_res = await client.post("/api/v1/auth/signup", json=payload)
    token = signup_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Get default project & queue
    proj_res = await client.get("/api/v1/projects", headers=headers)
    project_id = proj_res.json()[0]["id"]

    q_res = await client.get(f"/api/v1/projects/{project_id}/queues", headers=headers)
    queue_id = q_res.json()[0]["id"]

    return {
        "headers": headers,
        "project_id": project_id,
        "queue_id": queue_id,
    }


@pytest.mark.asyncio
async def test_job_immediate_creation(client, auth_setup):
    """Verify immediate job ingestion."""
    headers = auth_setup["headers"]
    queue_id = auth_setup["queue_id"]

    payload = {
        "name": "generate_report_pdf",
        "payload": {"report_type": "quarterly", "year": 2026},
        "priority": 40,
        "max_retries": 3,
        "tags": ["reports", "pdf"],
    }
    res = await client.post(f"/api/v1/queues/{queue_id}/jobs", headers=headers, json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "generate_report_pdf"
    assert data["status"] == "queued"
    assert data["priority"] == 40
    assert data["payload"]["year"] == 2026
    assert "pdf" in data["tags"]


@pytest.mark.asyncio
async def test_job_delayed_creation(client, auth_setup):
    """Verify scheduled delayed job submission."""
    headers = auth_setup["headers"]
    queue_id = auth_setup["queue_id"]

    payload = {
        "name": "send_marketing_blast",
        "payload": {"campaign_id": "summer_promo"},
        "delay_seconds": 3600,  # 1 hour delay
    }
    res = await client.post(f"/api/v1/queues/{queue_id}/jobs", headers=headers, json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "scheduled"
    assert data["run_at"] is not None


@pytest.mark.asyncio
async def test_job_idempotency_deduplication(client, auth_setup):
    """Verify client idempotency key prevents duplicate job creation."""
    headers = auth_setup["headers"]
    queue_id = auth_setup["queue_id"]
    idempotency_key = f"order-proc-{uuid.uuid4().hex}"

    job_payload = {
        "name": "charge_customer_card",
        "payload": {"amount": 500, "customer": "cust_123"},
    }

    # First submission with Idempotency-Key header
    req_headers = {**headers, "Idempotency-Key": idempotency_key}
    res1 = await client.post(f"/api/v1/queues/{queue_id}/jobs", headers=req_headers, json=job_payload)
    assert res1.status_code == 201
    job1_id = res1.json()["id"]

    # Second submission with same Idempotency-Key header
    res2 = await client.post(f"/api/v1/queues/{queue_id}/jobs", headers=req_headers, json=job_payload)
    assert res2.status_code == 201
    job2_id = res2.json()["id"]

    # Must return exact same job ID
    assert job1_id == job2_id


@pytest.mark.asyncio
async def test_batch_job_submission(client, auth_setup):
    """Verify batch job creation in single atomic transaction."""
    headers = auth_setup["headers"]
    queue_id = auth_setup["queue_id"]

    batch_payload = {
        "jobs": [
            {"name": f"batch_task_{i}", "payload": {"index": i}, "priority": 10 + i}
            for i in range(25)
        ]
    }
    res = await client.post(f"/api/v1/queues/{queue_id}/jobs/batch", headers=headers, json=batch_payload)
    assert res.status_code == 201
    created_jobs = res.json()
    assert len(created_jobs) == 25
    assert created_jobs[0]["name"] == "batch_task_0"
    assert created_jobs[24]["name"] == "batch_task_24"


@pytest.mark.asyncio
async def test_job_filtering_and_pagination(client, auth_setup):
    """Verify job listing with status filter, search, and pagination."""
    headers = auth_setup["headers"]
    queue_id = auth_setup["queue_id"]

    # Submit a tagged search job
    await client.post(
        f"/api/v1/queues/{queue_id}/jobs",
        headers=headers,
        json={"name": "unique_searchable_task", "payload": {}, "tags": ["search-tag"]},
    )

    # Filter by tag
    res_tag = await client.get("/api/v1/jobs?tag=search-tag", headers=headers)
    assert res_tag.status_code == 200
    tag_data = res_tag.json()
    assert tag_data["total"] >= 1
    assert any(j["name"] == "unique_searchable_task" for j in tag_data["items"])

    # Search by keyword
    res_search = await client.get("/api/v1/jobs?search=unique_searchable", headers=headers)
    assert res_search.status_code == 200
    assert len(res_search.json()["items"]) >= 1


@pytest.mark.asyncio
async def test_job_cancel_and_retry(client, auth_setup):
    """Verify cancelling a queued job and manually retrying it."""
    headers = auth_setup["headers"]
    queue_id = auth_setup["queue_id"]

    # Create job
    create_res = await client.post(
        f"/api/v1/queues/{queue_id}/jobs",
        headers=headers,
        json={"name": "cancellable_job", "payload": {}},
    )
    job_id = create_res.json()["id"]

    # Cancel job
    cancel_res = await client.post(f"/api/v1/jobs/{job_id}/cancel", headers=headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"

    # Retry job
    retry_res = await client.post(f"/api/v1/jobs/{job_id}/retry", headers=headers)
    assert retry_res.status_code == 200
    assert retry_res.json()["status"] == "queued"
