import pytest
import uuid


@pytest.fixture
async def org_admin_user(client):
    """Owner / Admin of Organization 1."""
    email = f"admin-{uuid.uuid4().hex[:6]}@example.com"
    res = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Org1 Admin",
            "organization_name": "Codity Enterprise",
        },
    )
    assert res.status_code == 201
    token = res.json()["access_token"]
    user_data = res.json()["user"]

    # Fetch default project
    headers = {"Authorization": f"Bearer {token}"}
    p_res = await client.get("/api/v1/projects", headers=headers)
    project_id = p_res.json()[0]["id"]

    # Create a test queue in project
    q_res = await client.post(
        f"/api/v1/projects/{project_id}/queues",
        headers=headers,
        json={"name": "core-events", "priority": 50, "concurrency_limit": 10},
    )
    assert q_res.status_code == 201
    queue_id = q_res.json()["id"]

    return {
        "headers": headers,
        "token": token,
        "user": user_data,
        "project_id": project_id,
        "queue_id": queue_id,
    }


@pytest.fixture
async def org_member_user(client, org_admin_user):
    """Developer / Member within Organization 1."""
    from backend.app.core.database import AsyncSessionLocal
    from backend.app.models import User, UserRole
    from backend.app.core.security import hash_password, create_access_token

    email = f"dev-{uuid.uuid4().hex[:6]}@example.com"
    async with AsyncSessionLocal() as session:
        user = User(
            email=email,
            hashed_password=hash_password("Password123!"),
            full_name="Developer Dave",
            org_id=uuid.UUID(org_admin_user["user"]["org_id"]),
            role=UserRole.MEMBER,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    token = create_access_token(subject=str(user_id))
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "token": token,
        "user_id": str(user_id),
    }


@pytest.fixture
async def org_viewer_user(client, org_admin_user):
    """Read-Only Viewer within Organization 1."""
    from backend.app.core.database import AsyncSessionLocal
    from backend.app.models import User, UserRole
    from backend.app.core.security import hash_password, create_access_token

    email = f"viewer-{uuid.uuid4().hex[:6]}@example.com"
    async with AsyncSessionLocal() as session:
        user = User(
            email=email,
            hashed_password=hash_password("Password123!"),
            full_name="Auditor Alice",
            org_id=uuid.UUID(org_admin_user["user"]["org_id"]),
            role=UserRole.VIEWER,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    token = create_access_token(subject=str(user_id))
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "token": token,
        "user_id": str(user_id),
    }


@pytest.fixture
async def foreign_org_user(client):
    """Admin of completely distinct Organization 2."""
    email = f"foreign-{uuid.uuid4().hex[:6]}@competitor.com"
    res = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Foreign Admin",
            "organization_name": "Competitor Corp",
        },
    )
    assert res.status_code == 201
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    p_res = await client.get("/api/v1/projects", headers=headers)
    project_id = p_res.json()[0]["id"]

    return {
        "headers": headers,
        "project_id": project_id,
    }


@pytest.mark.asyncio
async def test_admin_full_privileges(client, org_admin_user):
    """Admin has complete administrative control: manage projects, queues, API keys, and workers."""
    headers = org_admin_user["headers"]
    project_id = org_admin_user["project_id"]
    queue_id = org_admin_user["queue_id"]

    # 1. Admin can create new project
    res_proj = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"name": "Billing Subsystem", "description": "Payment microservice"},
    )
    assert res_proj.status_code == 201
    new_proj_id = res_proj.json()["id"]

    # 2. Admin can rename project
    res_rename = await client.put(
        f"/api/v1/projects/{new_proj_id}",
        headers=headers,
        json={"name": "Global Billing Subsystem"},
    )
    assert res_rename.status_code == 200
    assert res_rename.json()["name"] == "Global Billing Subsystem"

    # 3. Admin can generate API key
    res_key = await client.post(
        f"/api/v1/projects/{new_proj_id}/api-keys",
        headers=headers,
        json={"name": "Billing SDK Key"},
    )
    assert res_key.status_code == 201
    assert "api_key" in res_key.json()

    # 4. Admin can pause and resume queue
    res_pause = await client.post(f"/api/v1/queues/{queue_id}/pause", headers=headers)
    assert res_pause.status_code == 200
    assert res_pause.json()["is_paused"] is True

    res_resume = await client.post(f"/api/v1/queues/{queue_id}/resume", headers=headers)
    assert res_resume.status_code == 200
    assert res_resume.json()["is_paused"] is False


@pytest.mark.asyncio
async def test_developer_member_permissions_and_restrictions(client, org_admin_user, org_member_user):
    """Developer/Member can submit/retry jobs and schedules, but CANNOT manage projects/queues/workers."""
    dev_headers = org_member_user["headers"]
    admin_headers = org_admin_user["headers"]
    project_id = org_admin_user["project_id"]
    queue_id = org_admin_user["queue_id"]

    # 1. Developer CAN submit a job
    res_job = await client.post(
        f"/api/v1/queues/{queue_id}/jobs",
        headers=dev_headers,
        json={"name": "email_task", "payload": {"to": "user@test.com"}},
    )
    assert res_job.status_code == 201
    job_id = res_job.json()["id"]

    # 2. Developer CAN cancel and retry the job
    res_cancel = await client.post(f"/api/v1/jobs/{job_id}/cancel", headers=dev_headers)
    assert res_cancel.status_code == 200

    res_retry = await client.post(f"/api/v1/jobs/{job_id}/retry", headers=dev_headers)
    assert res_retry.status_code == 200

    # 3. Developer CANNOT create a project (Forbidden 403)
    res_proj_deny = await client.post(
        "/api/v1/projects",
        headers=dev_headers,
        json={"name": "Unauthorized Project"},
    )
    assert res_proj_deny.status_code == 403

    # 4. Developer CANNOT update project
    res_update_deny = await client.put(
        f"/api/v1/projects/{project_id}",
        headers=dev_headers,
        json={"name": "Hacked Name"},
    )
    assert res_update_deny.status_code == 403

    # 5. Developer CANNOT create/pause/delete queues
    res_q_deny = await client.post(
        f"/api/v1/projects/{project_id}/queues",
        headers=dev_headers,
        json={"name": "unauthorized-q"},
    )
    assert res_q_deny.status_code == 403

    res_pause_deny = await client.post(f"/api/v1/queues/{queue_id}/pause", headers=dev_headers)
    assert res_pause_deny.status_code == 403

    # 6. Developer CANNOT generate API keys
    res_key_deny = await client.post(
        f"/api/v1/projects/{project_id}/api-keys",
        headers=dev_headers,
        json={"name": "Unauthorized Key"},
    )
    assert res_key_deny.status_code == 403


@pytest.mark.asyncio
async def test_viewer_read_only_protection(client, org_admin_user, org_viewer_user):
    """Viewer role is strictly read-only: can view data but all mutations return 403 Forbidden."""
    viewer_headers = org_viewer_user["headers"]
    queue_id = org_admin_user["queue_id"]
    project_id = org_admin_user["project_id"]

    # 1. Viewer CAN list projects, queues, and jobs
    res_projs = await client.get("/api/v1/projects", headers=viewer_headers)
    assert res_projs.status_code == 200

    res_queues = await client.get(f"/api/v1/projects/{project_id}/queues", headers=viewer_headers)
    assert res_queues.status_code == 200

    res_jobs = await client.get("/api/v1/jobs", headers=viewer_headers)
    assert res_jobs.status_code == 200

    # 2. Viewer CANNOT submit jobs (403 Forbidden)
    res_sub_deny = await client.post(
        f"/api/v1/queues/{queue_id}/jobs",
        headers=viewer_headers,
        json={"name": "unauthorized_job", "payload": {}},
    )
    assert res_sub_deny.status_code == 403

    # 3. Viewer CANNOT create batches (403 Forbidden)
    res_batch_deny = await client.post(
        f"/api/v1/queues/{queue_id}/batches",
        headers=viewer_headers,
        json={"name": "unauthorized_batch", "jobs": [{"name": "j1", "payload": {}}]},
    )
    assert res_batch_deny.status_code == 403

    # 4. Viewer CANNOT create cron schedules (403 Forbidden)
    res_sched_deny = await client.post(
        f"/api/v1/queues/{queue_id}/schedules",
        headers=viewer_headers,
        json={"name": "unauthorized_cron", "cron_expression": "0 * * * *", "job_name": "cron_job", "job_payload": {}},
    )
    assert res_sched_deny.status_code == 403


@pytest.mark.asyncio
async def test_cross_tenant_multi_tenant_isolation_barrier(client, org_admin_user, foreign_org_user):
    """
    CRITICAL SECURITY BARRIER:
    User in Org A / Project A CANNOT access Org B / Project B resources
    even if they know or brute-force the exact UUID!
    """
    org1_headers = org_admin_user["headers"]
    org1_queue_id = org_admin_user["queue_id"]
    org1_project_id = org_admin_user["project_id"]

    foreign_headers = foreign_org_user["headers"]

    # 1. Create a confidential job in Org 1
    res_job = await client.post(
        f"/api/v1/queues/{org1_queue_id}/jobs",
        headers=org1_headers,
        json={"name": "secret_payroll_job", "payload": {"salary": 500000}},
    )
    assert res_job.status_code == 201
    job_id = res_job.json()["id"]

    # 2. Foreign User attempts to inspect Org 1's project -> 404 / 403 Forbidden
    res_peek_proj = await client.get(f"/api/v1/projects/{org1_project_id}", headers=foreign_headers)
    assert res_peek_proj.status_code == 404

    # 3. Foreign User attempts to inspect Org 1's queue -> 404 Not Found
    res_peek_queue = await client.get(f"/api/v1/queues/{org1_queue_id}", headers=foreign_headers)
    assert res_peek_queue.status_code == 404

    # 4. Foreign User attempts to submit a job to Org 1's queue -> 404 Not Found
    res_inject_job = await client.post(
        f"/api/v1/queues/{org1_queue_id}/jobs",
        headers=foreign_headers,
        json={"name": "injected_job", "payload": {}},
    )
    assert res_inject_job.status_code == 404

    # 5. Foreign User attempts to inspect or cancel Org 1's confidential job -> 404 Not Found
    res_peek_job = await client.get(f"/api/v1/jobs/{job_id}", headers=foreign_headers)
    assert res_peek_job.status_code == 404

    res_cancel_job = await client.post(f"/api/v1/jobs/{job_id}/cancel", headers=foreign_headers)
    assert res_cancel_job.status_code == 404
