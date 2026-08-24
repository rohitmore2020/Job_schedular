import os
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def test_docker_compose_file_validity():
    """Verify docker-compose.yml exists, parses as valid YAML, and contains all required services."""
    compose_path = REPO_ROOT / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml does not exist"

    with open(compose_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    assert "services" in config, "docker-compose.yml missing 'services' block"
    services = config["services"]

    # Verify all 5 core distributed services are defined
    expected_services = ["postgres", "api", "worker", "reaper_scheduler", "frontend"]
    for s in expected_services:
        assert s in services, f"Service '{s}' missing in docker-compose.yml"

    # Verify postgres health check
    pg = services["postgres"]
    assert "healthcheck" in pg
    assert "test" in pg["healthcheck"]
    assert any("pg_isready" in str(cmd) for cmd in pg["healthcheck"]["test"])

    # Verify API depends on healthy postgres
    api = services["api"]
    assert "depends_on" in api
    assert "postgres" in api["depends_on"]
    assert api["depends_on"]["postgres"].get("condition") == "service_healthy"

    # Verify Worker depends on healthy postgres
    worker = services["worker"]
    assert "depends_on" in worker
    assert "postgres" in worker["depends_on"]
    assert worker["depends_on"]["postgres"].get("condition") == "service_healthy"

    # Verify persistent volume
    assert "volumes" in config
    assert "postgres_data" in config["volumes"]


def test_dockerfile_backend_structure():
    """Verify docker/Dockerfile.backend has valid stages and requirements."""
    df_path = REPO_ROOT / "docker" / "Dockerfile.backend"
    assert df_path.exists()

    content = df_path.read_text()
    assert "FROM python:3.11-slim" in content
    assert "WORKDIR /app" in content
    assert "COPY backend/requirements.txt" in content
    assert "COPY alembic" in content
    assert "EXPOSE 8000" in content


def test_dockerfile_worker_structure():
    """Verify docker/Dockerfile.worker has valid stages and worker entrypoint."""
    df_path = REPO_ROOT / "docker" / "Dockerfile.worker"
    assert df_path.exists()

    content = df_path.read_text()
    assert "FROM python:3.11-slim" in content
    assert "WORKDIR /app" in content
    assert "COPY worker/" in content
    assert "CMD [\"python\", \"-m\", \"worker.main\"]" in content


def test_dockerfile_frontend_multi_stage_structure():
    """Verify docker/Dockerfile.frontend uses multi-stage node builder -> nginx alpine."""
    df_path = REPO_ROOT / "docker" / "Dockerfile.frontend"
    assert df_path.exists()

    content = df_path.read_text()
    assert "FROM node:20-alpine AS builder" in content
    assert "FROM nginx:alpine" in content
    assert "COPY --from=builder /app/dist /usr/share/nginx/html" in content
    assert "COPY docker/nginx.conf /etc/nginx/conf.d/default.conf" in content
    assert "EXPOSE 80" in content


def test_nginx_reverse_proxy_and_websocket_config():
    """Verify docker/nginx.conf correctly routes REST API and WebSocket upgrades."""
    nginx_path = REPO_ROOT / "docker" / "nginx.conf"
    assert nginx_path.exists()

    content = nginx_path.read_text()
    assert "location /api/" in content
    assert "proxy_pass http://api:8000;" in content
    assert "location /api/v1/ws" in content
    assert "proxy_set_header Upgrade $http_upgrade;" in content
    assert 'proxy_set_header Connection "Upgrade";' in content
