import pytest
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from starlette.testclient import TestClient

from backend.app.main import app
from backend.app.models import (
    Organization,
    Project,
    Queue,
    ScheduledJob,
    Job,
    JobStatus,
)
from worker.app.cron import CronDispatcher


@pytest.fixture
async def queue_fixture(db_session):
    org = Organization(name="Cron Org", slug=f"cron-org-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    proj = Project(org_id=org.id, name="Cron Proj", slug=f"c-proj-{uuid.uuid4().hex[:6]}")
    db_session.add(proj)
    await db_session.flush()

    queue = Queue(
        project_id=proj.id,
        name=f"cron-queue-{uuid.uuid4().hex[:6]}",
        priority=50,
        concurrency_limit=10,
        is_paused=False,
    )
    db_session.add(queue)
    await db_session.commit()
    await db_session.refresh(queue)
    return queue


def test_cron_expression_calculation():
    """Verify Cron next fire calculation."""
    # Run every 10 minutes
    now_utc = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
    next_fire = CronDispatcher.compute_next_run("*/10 * * * *", now_utc)
    assert next_fire == datetime(2026, 8, 22, 12, 10, 0, tzinfo=timezone.utc)

    # Daily at midnight
    next_midnight = CronDispatcher.compute_next_run("0 0 * * *", now_utc)
    assert next_midnight == datetime(2026, 8, 23, 0, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_cron_dispatcher_evaluates_and_enqueues_child_job(db_session, queue_fixture):
    """Verify CronDispatcher finds due schedules, enqueues child jobs, and advances next_run_at."""
    queue = queue_fixture
    now_utc = datetime.now(timezone.utc)

    # Create due schedule (next_run_at 10s in past)
    schedule = ScheduledJob(
        project_id=queue.project_id,
        queue_id=queue.id,
        name="calculate_report",
        cron_expression="*/15 * * * *",
        payload={"period": "quarterly"},
        priority=60,
        is_active=True,
        next_run_at=now_utc - timedelta(seconds=10),
    )
    db_session.add(schedule)
    await db_session.commit()

    dispatcher = CronDispatcher()
    dispatched = await dispatcher.dispatch_due_schedules(db_session)
    assert dispatched >= 1

    # Verify Job was inserted into this specific queue
    job_stmt = select(Job).where(Job.queue_id == queue.id)
    job_res = await db_session.execute(job_stmt)
    child_job = job_res.scalar_one()

    assert child_job.name == "calculate_report"
    assert child_job.status == JobStatus.QUEUED
    assert child_job.priority == 60
    assert child_job.payload["period"] == "quarterly"
    assert "cron" in child_job.tags

    # Verify schedule next_run_at advanced
    await db_session.refresh(schedule)
    assert schedule.next_run_at > now_utc
    assert schedule.total_runs_count == 1


@pytest.mark.asyncio
async def test_schedules_crud_and_pause_resume(client):
    """Verify Schedule REST APIs: create, pause, resume, delete."""
    # 1. Sign up user
    email = f"cron-user-{uuid.uuid4().hex[:6]}@test.com"
    signup_res = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": "Cron User", "organization_name": "Cron Co"},
    )
    token = signup_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Get default queue
    proj_res = await client.get("/api/v1/projects", headers=headers)
    project_id = proj_res.json()[0]["id"]
    q_res = await client.get(f"/api/v1/projects/{project_id}/queues", headers=headers)
    queue_id = q_res.json()[0]["id"]

    # 3. Create schedule with invalid cron -> 422
    bad_res = await client.post(
        f"/api/v1/queues/{queue_id}/schedules",
        headers=headers,
        json={"name": "bad_cron_task", "cron_expression": "invalid-cron-string"},
    )
    assert bad_res.status_code == 422

    # 4. Create valid schedule
    create_res = await client.post(
        f"/api/v1/queues/{queue_id}/schedules",
        headers=headers,
        json={
            "name": "hourly_cleanup",
            "cron_expression": "0 * * * *",
            "payload": {"cleanup_target": "temp_files"},
            "priority": 25,
        },
    )
    assert create_res.status_code == 201
    schedule_data = create_res.json()
    schedule_id = schedule_data["id"]
    assert schedule_data["is_active"] == True
    assert schedule_data["cron_expression"] == "0 * * * *"

    # 5. Pause schedule
    pause_res = await client.post(f"/api/v1/schedules/{schedule_id}/pause", headers=headers)
    assert pause_res.status_code == 200
    assert pause_res.json()["is_active"] == False

    # 6. Resume schedule
    resume_res = await client.post(f"/api/v1/schedules/{schedule_id}/resume", headers=headers)
    assert resume_res.status_code == 200
    assert resume_res.json()["is_active"] == True

    # 7. Delete schedule
    del_res = await client.delete(f"/api/v1/schedules/{schedule_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["message"] == "Recurring schedule deleted"


def test_websocket_endpoint():
    """Verify WebSocket endpoint connectivity and ping-pong loop using Starlette TestClient."""
    sync_client = TestClient(app)
    with sync_client.websocket_connect("/api/v1/ws") as websocket:
        init_msg = websocket.receive_json()
        assert init_msg["event"] == "connected"

        websocket.send_text("ping")
        resp = websocket.receive_text()
        assert resp == "pong"
