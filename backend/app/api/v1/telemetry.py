import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user
from backend.app.models import User
from backend.app.schemas.telemetry import FullTelemetryResponse
from backend.app.services.telemetry_service import TelemetryService

router = APIRouter(prefix="/telemetry", tags=["Telemetry & Observability"])


@router.get(
    "",
    response_model=FullTelemetryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get full system, queue, worker, and performance telemetry metrics",
)
async def get_telemetry(
    project_id: Optional[uuid.UUID] = Query(None, description="Optional project ID filter"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve comprehensive live observability metrics:
    - **System:** Total jobs, Jobs/sec, Success Rate %, Failure Rate %, Retry Rate %, DLQ Rate %.
    - **Queues:** Queue depth, Oldest job age, Average wait time, Throughput, Running jobs, Concurrency utilization.
    - **Workers:** Workers online, busy, idle, average CPU %, average RAM MB.
    """
    return await TelemetryService.get_telemetry(db, current_user, project_id=project_id)
