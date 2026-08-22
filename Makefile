.PHONY: help setup run-api run-worker run-scheduler migrate reset-db seed test docker-up docker-down clean

VENV = .venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip
UVICORN = $(VENV)/bin/uvicorn
ALEMBIC = $(VENV)/bin/alembic
PYTEST = $(VENV)/bin/pytest

help:
	@echo "Distributed Job Scheduler Developer Commands:"
	@echo "  make setup          - Create virtualenv and install all dependencies"
	@echo "  make run-api        - Start FastAPI backend server on http://localhost:8000"
	@echo "  make run-worker     - Start distributed worker daemon process"
	@echo "  make run-scheduler  - Start reaper and cron scheduler daemon"
	@echo "  make migrate        - Apply Alembic database migrations"
	@echo "  make seed           - Seed database with demo data"
	@echo "  make reset-db       - Drop, recreate, migrate, and seed the database"
	@echo "  make test           - Run automated tests and concurrency suites"
	@echo "  make docker-up      - Spin up all services via Docker Compose"
	@echo "  make docker-down    - Stop and remove Docker containers"
	@echo "  make clean          - Remove pycache and temporary build artifacts"

setup:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements.txt

run-api:
	$(UVICORN) backend.app.main:app --reload --host 0.0.0.0 --port 8000

run-worker:
	$(PYTHON) -m worker.main

run-scheduler:
	$(PYTHON) -m worker.scheduler_main

migrate:
	$(ALEMBIC) upgrade head

seed:
	$(PYTHON) scripts/seed_demo.py

reset-db:
	$(PYTHON) scripts/reset_db.py

test:
	$(PYTEST) tests/ -v -s

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
