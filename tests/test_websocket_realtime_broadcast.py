import pytest
import uuid
import json
from datetime import datetime, timezone
from starlette.testclient import TestClient

from backend.app.main import app
from backend.app.core.database import AsyncSessionLocal
from backend.app.models import (
    Organization,
    Project,
    Queue,
    Job,
    User,
    UserRole,
    JobStatus,
    RetryStrategy,
)
from backend.app.schemas.job import JobCreate
from backend.app.services.job_service import JobService
from backend.app.services.queue_service import QueueService
from worker.app.engine.runner import TaskRunner
from worker.app.heartbeat import WorkerHeartbeatEmitter
from worker.app.tasks.registry import task_registry


@task_registry.register("ws_test_task")
async def handle_ws_test_task(payload: dict):
    return {"status": "broadcast_verified", "data": payload.get("data")}


@pytest.fixture
async def ws_test_env():
    """Sets up an isolated org, project, queue, and user for WebSocket tests."""
    async with AsyncSessionLocal() as session:
        org = Organization(name="WS Org", slug=f"ws-org-{uuid.uuid4().hex[:6]}")
        session.add(org)
        await session.flush()

        project = Project(
            org_id=org.id, name="WS Proj", slug=f"ws-proj-{uuid.uuid4().hex[:6]}"
        )
        session.add(project)
        await session.flush()

        queue = Queue(
            project_id=project.id,
            name=f"ws-queue-{uuid.uuid4().hex[:6]}",
            priority=50,
            concurrency_limit=10,
            is_paused=False,
        )
        session.add(queue)
        await session.flush()

        user = User(
            email=f"ws-user-{uuid.uuid4().hex[:6]}@example.com",
            hashed_password="hashed_pwd",
            full_name="WS Tester",
            role=UserRole.ADMIN,
            org_id=org.id,
        )
        session.add(user)
        await session.commit()
        await session.refresh(queue)
        await session.refresh(user)

        return {
            "org_id": org.id,
            "project_id": project.id,
            "queue_id": queue.id,
            "queue_name": queue.name,
            "user": user,
        }


# =========================================================================
# TEST 1: WebSocket Receives Real-Time Push on Job Creation
# =========================================================================
@pytest.mark.asyncio
async def test_ws_broadcast_on_job_creation(ws_test_env):
    client = TestClient(app)
    user = ws_test_env["user"]
    queue_id = ws_test_env["queue_id"]

    with client.websocket_connect("/api/v1/ws") as websocket:
        # Initial greeting event
        greeting = websocket.receive_json()
        assert greeting["event"] == "connected"

        # Create job
        async with AsyncSessionLocal() as session:
            job_req = JobCreate(
                name="ws_test_task",
                priority=10,
                payload={"data": "realtime_push_check"},
            )
            created_job = await JobService.create_job(
                session, user, queue_id, job_req
            )

        # Verify WebSocket received the real-time push event
        event = websocket.receive_json()
        assert event["event"] == "job_created"
        assert event["data"]["job_id"] == str(created_job.id)
        assert event["data"]["status"] == "queued"
        assert event["data"]["name"] == "ws_test_task"


# =========================================================================
# TEST 2: WebSocket Receives Real-Time Push on Execution (Running & Completed)
# =========================================================================
@pytest.mark.asyncio
async def test_ws_broadcast_on_execution_lifecycle(ws_test_env):
    client = TestClient(app)
    queue_id = ws_test_env["queue_id"]
    worker_id = f"worker-ws-{uuid.uuid4().hex[:6]}"

    async with AsyncSessionLocal() as session:
        job = Job(
            queue_id=queue_id,
            name="ws_test_task",
            status=JobStatus.RUNNING,
            payload={"data": "execute_lifecycle"},
            attempt_count=1,
            lease_token=uuid.uuid4(),
            run_at=datetime.now(timezone.utc),
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    with client.websocket_connect("/api/v1/ws") as websocket:
        _ = websocket.receive_json()  # Consume initial "connected"

        async with AsyncSessionLocal() as session:
            db_job = await session.get(Job, job_id)
            await TaskRunner.execute_job(session, db_job, worker_id)

        # Expect event 1: job_running
        event_running = websocket.receive_json()
        assert event_running["event"] == "job_running"
        assert event_running["data"]["job_id"] == str(job_id)
        assert event_running["data"]["worker_id"] == worker_id

        # Expect event 2: job_completed
        event_completed = websocket.receive_json()
        assert event_completed["event"] == "job_completed"
        assert event_completed["data"]["job_id"] == str(job_id)
        assert event_completed["data"]["status"] == "completed"
        assert "duration_ms" in event_completed["data"]


# =========================================================================
# TEST 3: WebSocket Multi-Client Broadcast (Two Browser Tabs Fanout)
# =========================================================================
@pytest.mark.asyncio
async def test_ws_multi_client_fanout_across_two_tabs(ws_test_env):
    client = TestClient(app)
    user = ws_test_env["user"]
    queue_id = ws_test_env["queue_id"]

    # Open Tab 1 and Tab 2 connections simultaneously
    with client.websocket_connect("/api/v1/ws") as tab1, client.websocket_connect("/api/v1/ws") as tab2:
        _ = tab1.receive_json()  # Tab 1 connected
        _ = tab2.receive_json()  # Tab 2 connected

        # Cancel a job and verify both tabs get notified simultaneously
        async with AsyncSessionLocal() as session:
            job = Job(
                queue_id=queue_id,
                name="ws_test_task",
                status=JobStatus.QUEUED,
                payload={},
                run_at=datetime.now(timezone.utc),
            )
            session.add(job)
            await session.commit()
            job_id = job.id

            await JobService.cancel_job(session, user, job_id)

        # Tab 1 assertion
        tab1_event = tab1.receive_json()
        assert tab1_event["event"] == "job_cancelled"
        assert tab1_event["data"]["job_id"] == str(job_id)
        assert tab1_event["data"]["status"] == "cancelled"

        # Tab 2 assertion
        tab2_event = tab2.receive_json()
        assert tab2_event["event"] == "job_cancelled"
        assert tab2_event["data"]["job_id"] == str(job_id)
        assert tab2_event["data"]["status"] == "cancelled"


# =========================================================================
# TEST 4: WebSocket Receives Worker Telemetry Heartbeat Push
# =========================================================================
@pytest.mark.asyncio
async def test_ws_broadcast_on_worker_heartbeat(ws_test_env):
    client = TestClient(app)
    worker_id = f"worker-hb-{uuid.uuid4().hex[:6]}"
    active_jobs = set()
    emitter = WorkerHeartbeatEmitter(worker_id, active_jobs)

    with client.websocket_connect("/api/v1/ws") as websocket:
        _ = websocket.receive_json()  # Connected

        # Create worker record first
        async with AsyncSessionLocal() as session:
            from backend.app.models import Worker, WorkerStatus
            worker = Worker(
                worker_id=worker_id,
                hostname="test-host",
                pid=12345,
                concurrency_limit=2,
                status=WorkerStatus.ALIVE,
                assigned_queues=["default"],
            )
            session.add(worker)
            await session.commit()

        # Emit one heartbeat
        async with AsyncSessionLocal() as session:
            await emitter.emit_once(session)

        # Verify push
        hb_event = websocket.receive_json()
        assert hb_event["event"] == "worker_heartbeat"
        assert hb_event["data"]["worker_id"] == worker_id
        assert "cpu_percent" in hb_event["data"]
        assert "memory_mb" in hb_event["data"]
