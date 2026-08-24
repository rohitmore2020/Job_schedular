import pytest
import uuid


@pytest.mark.asyncio
async def test_signup_success(client):
    """Verify registration of a new organization and admin user."""
    email = f"user-{uuid.uuid4().hex[:6]}@example.com"
    payload = {
        "email": email,
        "password": "Password123!",
        "full_name": "Alice Engineer",
        "organization_name": "Alice Technologies",
    }
    response = await client.post("/api/v1/auth/signup", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == email
    assert data["user"]["full_name"] == "Alice Engineer"
    assert data["user"]["role"] == "admin"
    assert data["organization"]["name"] == "Alice Technologies"


@pytest.mark.asyncio
async def test_signup_duplicate_email(client):
    """Verify signup fails with 400 when email is already registered."""
    email = f"dup-{uuid.uuid4().hex[:6]}@example.com"
    payload = {
        "email": email,
        "password": "Password123!",
        "full_name": "Bob Dev",
        "organization_name": "Bob Labs",
    }
    res1 = await client.post("/api/v1/auth/signup", json=payload)
    assert res1.status_code == 201

    res2 = await client.post("/api/v1/auth/signup", json=payload)
    assert res2.status_code == 400
    assert "already exists" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_login_success_and_invalid_password(client):
    """Verify login with valid vs invalid passwords."""
    email = f"login-{uuid.uuid4().hex[:6]}@example.com"
    signup_payload = {
        "email": email,
        "password": "CorrectPassword123",
        "full_name": "Charlie Admin",
        "organization_name": "Charlie Cloud",
    }
    await client.post("/api/v1/auth/signup", json=signup_payload)

    # Valid Login
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "CorrectPassword123"},
    )
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()

    # Invalid Password
    bad_login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword!"},
    )
    assert bad_login_res.status_code == 401
    assert "Invalid email or password" in bad_login_res.json()["detail"]


@pytest.mark.asyncio
async def test_get_me_authenticated_and_unauthorized(client):
    """Verify /auth/me returns current user when authenticated, 401 when unauthorized."""
    email = f"me-{uuid.uuid4().hex[:6]}@example.com"
    signup_payload = {
        "email": email,
        "password": "SecretPassword123",
        "full_name": "Diana Engineer",
        "organization_name": "Diana Systems",
    }
    signup_res = await client.post("/api/v1/auth/signup", json=signup_payload)
    token = signup_res.json()["access_token"]

    # Authenticated call
    headers = {"Authorization": f"Bearer {token}"}
    me_res = await client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    data = me_res.json()
    assert data["user"]["email"] == email
    assert data["organization"]["name"] == "Diana Systems"

    # Unauthorized call without token
    unauth_res = await client.get("/api/v1/auth/me")
    assert unauth_res.status_code == 401

    # Unauthorized call with garbage token
    bad_token_res = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer fake_token_abc"})
    assert bad_token_res.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_flow(client):
    """Verify refresh token rotation."""
    email = f"refresh-{uuid.uuid4().hex[:6]}@example.com"
    signup_payload = {
        "email": email,
        "password": "Password12345",
        "full_name": "Eve Developer",
        "organization_name": "Eve AI",
    }
    signup_res = await client.post("/api/v1/auth/signup", json=signup_payload)
    refresh_token = signup_res.json()["refresh_token"]

    # Rotate refresh token
    refresh_res = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_res.status_code == 200
    new_tokens = refresh_res.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens

    # Verify newly issued access token works on /auth/me
    headers = {"Authorization": f"Bearer {new_tokens['access_token']}"}
    me_res = await client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["user"]["email"] == email
