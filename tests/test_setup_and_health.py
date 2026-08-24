import pytest
from sqlalchemy import text
from backend.app.core.config import settings


@pytest.mark.asyncio
async def test_database_connection(db_session):
    """Verify that PostgreSQL is accessible through the async SQLAlchemy engine."""
    result = await db_session.execute(text("SELECT 1 AS ready"))
    row = result.fetchone()
    assert row is not None
    assert row[0] == 1


@pytest.mark.asyncio
async def test_health_check_endpoint(client):
    """Verify that the FastAPI health check endpoint returns 200 and healthy DB status."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["environment"] == settings.ENVIRONMENT


@pytest.mark.asyncio
async def test_root_endpoint(client):
    """Verify root endpoint returns service metadata."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == settings.PROJECT_NAME
    assert data["docs"] == "/docs"
