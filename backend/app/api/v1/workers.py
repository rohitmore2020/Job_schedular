from typing import List
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user
from backend.app.models import User, Worker, WorkerHeartbeat, WorkerStatus
from backend.app.schemas.worker import WorkerResponse, WorkerHeartbeatResponse

router = APIRouter(prefix="/workers", tags=["Workers"])


@router.get(
    "",
    response_model=List[WorkerResponse],
    status_code=status.HTTP_200_OK,
    summary="List all registered worker nodes and their status",
)
async def list_workers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve worker fleet details, current concurrency limits, and liveness.
    """
    stmt = select(Worker).order_by(Worker.started_at.desc())
    result = await db.execute(stmt)
    workers = result.scalars().all()

    now_utc = datetime.now(timezone.utc)
    threshold = now_utc - timedelta(seconds=30)

    responses = []
    for w in workers:
        is_alive = (w.status == WorkerStatus.ALIVE) and (w.last_heartbeat_at >= threshold)
        resp = WorkerResponse.model_validate(w)
        resp.is_alive = is_alive
        responses.append(resp)
    return responses


@router.get(
    "/{worker_id}/heartbeats",
    response_model=List[WorkerHeartbeatResponse],
    status_code=status.HTTP_200_OK,
    summary="Get recent telemetry heartbeats for a worker",
)
async def get_worker_heartbeats(
    worker_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve CPU and RAM usage time-series data for a worker.
    """
    stmt = (
        select(WorkerHeartbeat)
        .where(WorkerHeartbeat.worker_id == worker_id)
        .order_by(desc(WorkerHeartbeat.timestamp))
        .limit(limit)
    )
    result = await db.execute(stmt)
    heartbeats = result.scalars().all()
    return [WorkerHeartbeatResponse.model_validate(h) for h in heartbeats]
