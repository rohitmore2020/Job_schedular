import pytest
import uuid


@pytest.fixture
async def auth_headers_user1(client):
    email = f"user1-{uuid.uuid4().hex[:6]}@test.com"
    payload = {
        "email": email,
        "password": "Password123!",
        "full_name": "Org 1 Admin",
        "organization_name": "Org One",
    }
    res = await client.post("/api/v1/auth/signup", json=payload)
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def auth_headers_user2(client):
    email = f"user2-{uuid.uuid4().hex[:6]}@test.com"
    payload = {
        "email": email,
        "password": "Password123!",
        "full_name": "Org 2 Admin",
        "organization_name": "Org Two",
    }
    res = await client.post("/api/v1/auth/signup", json=payload)
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_project_crud_and_multi_tenant_isolation(client, auth_headers_user1, auth_headers_user2):
    """Verify project lifecycle and strict multi-tenant isolation between different organizations."""
    # 1. User 1 creates a project
    create_res = await client.post(
        "/api/v1/projects",
        headers=auth_headers_user1,
        json={"name": "Billing Engine", "description": "Handles recurring payments"},
    )
    assert create_res.status_code == 201
    project1 = create_res.json()
    assert project1["name"] == "Billing Engine"
    project_id = project1["id"]

    # 2. User 1 lists projects
    list_res = await client.get("/api/v1/projects", headers=auth_headers_user1)
    assert list_res.status_code == 200
    projects = list_res.json()
    # Should include default project + the new one
    assert any(p["id"] == project_id for p in projects)

    # 3. User 2 (different organization) cannot access User 1's project
    forbidden_res = await client.get(f"/api/v1/projects/{project_id}", headers=auth_headers_user2)
    assert forbidden_res.status_code == 404

    # 4. User 1 updates project
    update_res = await client.put(
        f"/api/v1/projects/{project_id}",
        headers=auth_headers_user1,
        json={"name": "Global Billing Engine", "description": "Updated description"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Global Billing Engine"


@pytest.mark.asyncio
async def test_project_api_key_generation(client, auth_headers_user1):
    """Verify generating and listing project API keys."""
    # Get user 1's projects
    proj_res = await client.get("/api/v1/projects", headers=auth_headers_user1)
    project_id = proj_res.json()[0]["id"]

    # Generate API key
    key_res = await client.post(
        f"/api/v1/projects/{project_id}/api-keys",
        headers=auth_headers_user1,
        json={"name": "SDK Server Key", "expires_in_days": 30},
    )
    assert key_res.status_code == 201
    key_data = key_res.json()
    assert "api_key" in key_data
    assert key_data["api_key"].startswith("cjs_live_")
    assert key_data["name"] == "SDK Server Key"

    # List API keys (should not leak full secret key in list)
    list_keys_res = await client.get(
        f"/api/v1/projects/{project_id}/api-keys",
        headers=auth_headers_user1,
    )
    assert list_keys_res.status_code == 200
    keys_list = list_keys_res.json()
    assert len(keys_list) >= 1
    assert "api_key" not in keys_list[0]
    assert "prefix" in keys_list[0]


@pytest.mark.asyncio
async def test_queue_lifecycle_and_pause_resume(client, auth_headers_user1):
    """Verify queue creation with retry policy, updating parameters, pausing and resuming."""
    # 1. Get project ID
    proj_res = await client.get("/api/v1/projects", headers=auth_headers_user1)
    project_id = proj_res.json()[0]["id"]

    # 2. Create Queue with custom exponential retry policy
    create_q_res = await client.post(
        f"/api/v1/projects/{project_id}/queues",
        headers=auth_headers_user1,
        json={
            "name": "webhook-dispatcher",
            "priority": 75,
            "concurrency_limit": 20,
            "rate_limit_rps": 50,
            "retry_policy": {
                "strategy": "exponential",
                "max_retries": 4,
                "initial_interval_sec": 3,
                "max_interval_sec": 600,
                "backoff_multiplier": 2.5,
                "jitter": True,
            },
        },
    )
    assert create_q_res.status_code == 201
    q_data = create_q_res.json()
    assert q_data["name"] == "webhook-dispatcher"
    assert q_data["priority"] == 75
    assert q_data["is_paused"] is False
    assert q_data["retry_policy"]["max_retries"] == 4
    queue_id = q_data["id"]

    # 3. List queues in project
    list_q_res = await client.get(
        f"/api/v1/projects/{project_id}/queues",
        headers=auth_headers_user1,
    )
    assert list_q_res.status_code == 200
    queues = list_q_res.json()
    assert any(q["id"] == queue_id for q in queues)

    # 4. Update queue settings
    update_q_res = await client.put(
        f"/api/v1/queues/{queue_id}",
        headers=auth_headers_user1,
        json={"priority": 90, "concurrency_limit": 25},
    )
    assert update_q_res.status_code == 200
    assert update_q_res.json()["priority"] == 90
    assert update_q_res.json()["concurrency_limit"] == 25

    # 5. Pause queue
    pause_res = await client.post(f"/api/v1/queues/{queue_id}/pause", headers=auth_headers_user1)
    assert pause_res.status_code == 200
    assert pause_res.json()["is_paused"] is True

    # 6. Resume queue
    resume_res = await client.post(f"/api/v1/queues/{queue_id}/resume", headers=auth_headers_user1)
    assert resume_res.status_code == 200
    assert resume_res.json()["is_paused"] is False

    # 7. Delete queue
    del_res = await client.delete(f"/api/v1/queues/{queue_id}", headers=auth_headers_user1)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # Confirm deleted
    get_deleted = await client.get(f"/api/v1/queues/{queue_id}", headers=auth_headers_user1)
    assert get_deleted.status_code == 404
