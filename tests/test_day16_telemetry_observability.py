import pytest
import uuid
from datetime import datetime, timezone


@pytest.fixture
async def auth_user_telemetry(client):
    email = f"telemetry-{uuid.uuid4().hex[:6]}@example.com"
    res = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Telemetry Admin",
            "organization_name": "Observability Corp",
        },
    )
    assert res.status_code == 201
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Fetch default project
    p_res = await client.get("/api/v1/projects", headers=headers)
    project_id = p_res.json()[0]["id"]

    # Create queue
    q_res = await client.post(
        f"/api/v1/projects/{project_id}/queues",
        headers=headers,
        json={"name": "telemetry-queue", "priority": 50, "concurrency_limit": 5},
    )
    assert q_res.status_code == 201
    queue_id = q_res.json()["id"]

    return {
        "headers": headers,
        "project_id": project_id,
        "queue_id": queue_id,
    }


@pytest.mark.asyncio
async def test_system_telemetry_metrics_and_rates(client, auth_user_telemetry):
    """Verify system-wide job counters, jobs/sec, success/failure/retry/DLQ rates."""
    headers = auth_user_telemetry["headers"]
    queue_id = auth_user_telemetry["queue_id"]
    project_id = auth_user_telemetry["project_id"]

    # 1. Submit jobs
    for i in range(5):
        await client.post(
            f"/api/v1/queues/{queue_id}/jobs",
            headers=headers,
            json={"name": f"telemetry_job_{i}", "payload": {"index": i}},
        )

    # 2. Fetch Telemetry
    res = await client.get(f"/api/v1/telemetry?project_id={project_id}", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert "system" in data
    assert "fleet" in data
    assert "queues" in data

    sys = data["system"]
    assert sys["total_jobs"] >= 5
    assert sys["queued_jobs"] >= 5
    assert isinstance(sys["jobs_per_sec"], float)
    assert isinstance(sys["success_rate_percent"], float)
    assert isinstance(sys["failure_rate_percent"], float)
    assert isinstance(sys["retry_rate_percent"], float)
    assert isinstance(sys["dlq_rate_percent"], float)


@pytest.mark.asyncio
async def test_queue_telemetry_depth_wait_times_and_utilization(client, auth_user_telemetry):
    """Verify queue depth, oldest job age, average wait time, and concurrency utilization %."""
    headers = auth_user_telemetry["headers"]
    queue_id = auth_user_telemetry["queue_id"]

    # 1. Enqueue jobs to create depth
    await client.post(
        f"/api/v1/queues/{queue_id}/jobs",
        headers=headers,
        json={"name": "depth_job_1", "payload": {}},
    )
    await client.post(
        f"/api/v1/queues/{queue_id}/jobs",
        headers=headers,
        json={"name": "depth_job_2", "payload": {}},
    )

    # 2. Get Queue stats
    res = await client.get(f"/api/v1/queues/{queue_id}", headers=headers)
    assert res.status_code == 200
    q_data = res.json()

    stats = q_data["stats"]
    assert stats["queue_depth"] >= 2
    assert stats["queued"] >= 2
    assert stats["concurrency_utilization_percent"] >= 0.0
    assert stats["oldest_job_age_seconds"] is not None
    assert stats["oldest_job_age_seconds"] >= 0.0


@pytest.mark.asyncio
async def test_worker_fleet_liveness_and_telemetry(client, auth_user_telemetry):
    """Verify worker fleet telemetry: heartbeat age, jobs processed, and failure count."""
    from backend.app.core.database import AsyncSessionLocal
    from backend.app.models import Worker, WorkerHeartbeat, WorkerStatus

    worker_id = f"test-telemetry-worker-{uuid.uuid4().hex[:4]}"
    now_utc = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        worker = Worker(
            worker_id=worker_id,
            hostname="worker-node-alpha",
            pid=12345,
            concurrency_limit=5,
            current_active_jobs=2,
            status=WorkerStatus.ALIVE,
            last_heartbeat_at=now_utc,
        )
        session.add(worker)
        session.add(
            WorkerHeartbeat(
                worker_id=worker_id,
                cpu_percent=24.5,
                memory_mb=256.0,
                active_jobs=2,
                timestamp=now_utc,
            )
        )
        await session.commit()

    headers = auth_user_telemetry["headers"]
    res = await client.get("/api/v1/workers", headers=headers)
    assert res.status_code == 200
    workers = res.json()

    target_worker = next((w for w in workers if w["worker_id"] == worker_id), None)
    assert target_worker is not None
    assert target_worker["is_alive"] is True
    assert target_worker["is_busy"] is True
    assert target_worker["is_idle"] is False
    assert target_worker["heartbeat_age_seconds"] >= 0.0
    assert "jobs_processed" in target_worker
    assert "failure_count" in target_worker


@pytest.mark.asyncio
async def test_job_detail_drawer_latency_breakdown(client, auth_user_telemetry):
    """Verify per-job latency breakdown (queue wait time, execution duration, retry count)."""
    headers = auth_user_telemetry["headers"]
    queue_id = auth_user_telemetry["queue_id"]

    # 1. Enqueue job
    res_job = await client.post(
        f"/api/v1/queues/{queue_id}/jobs",
        headers=headers,
        json={"name": "latency_test_task", "payload": {"foo": "bar"}},
    )
    assert res_job.status_code == 201
    job_id = res_job.json()["id"]

    # 2. Inspect job detail
    res_detail = await client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert res_detail.status_code == 200
    detail = res_detail.json()

    assert "queue_wait_ms" in detail
    assert "execution_duration_ms" in detail
    assert "retry_count" in detail
    assert "total_execution_time_ms" in detail
    assert detail["retry_count"] == 0
