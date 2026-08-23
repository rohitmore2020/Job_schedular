from fastapi import APIRouter
from backend.app.api.v1.auth import router as auth_router
from backend.app.api.v1.projects import router as projects_router
from backend.app.api.v1.queues import router as queues_router
from backend.app.api.v1.jobs import router as jobs_router
from backend.app.api.v1.workers import router as workers_router
from backend.app.api.v1.dlq import router as dlq_router
from backend.app.api.v1.schedules import router as schedules_router
from backend.app.api.v1.batches import router as batches_router
from backend.app.api.v1.telemetry import router as telemetry_router
from backend.app.api.v1.ws import router as ws_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(projects_router)
api_router.include_router(queues_router)
api_router.include_router(jobs_router)
api_router.include_router(batches_router)
api_router.include_router(telemetry_router)
api_router.include_router(workers_router)
api_router.include_router(dlq_router)
api_router.include_router(schedules_router)
api_router.include_router(ws_router)
