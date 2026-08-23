from typing import List
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy import select, desc, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user, require_admin
from backend.app.models import User, Worker, WorkerHeartbeat, WorkerStatus, JobExecution, ExecutionStatus
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

    # Aggregate processed jobs & failure counts per worker
    exec_stmt = select(
        JobExecution.worker_id,
        func.count(JobExecution.id).label("total_processed"),
        func.count(case((JobExecution.status != ExecutionStatus.SUCCESS, 1))).label("total_failed"),
    ).group_by(JobExecution.worker_id)
    exec_res = await db.execute(exec_stmt)
    worker_exec_map = {row[0]: (row[1] or 0, row[2] or 0) for row in exec_res.fetchall()}

    responses = []
    for w in workers:
        is_alive = (w.status == WorkerStatus.ALIVE) and (w.last_heartbeat_at >= threshold)
        age_sec = max(0.0, round((now_utc - w.last_heartbeat_at).total_seconds(), 1))
        processed_count, failed_count = worker_exec_map.get(w.worker_id, (0, 0))

        resp = WorkerResponse.model_validate(w)
        resp.is_alive = is_alive
        resp.heartbeat_age_seconds = age_sec
        resp.jobs_processed = processed_count
        resp.failure_count = failed_count
        resp.is_busy = w.current_active_jobs > 0
        resp.is_idle = w.current_active_jobs == 0
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


@router.post(
    "/{worker_id}/drain",
    response_model=WorkerResponse,
    status_code=status.HTTP_200_OK,
    summary="Drain a worker node (Admin only)",
)
async def drain_worker(
    worker_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Signal a worker node to drain: finish executing active jobs but claim no new ones.
    """
    stmt = select(Worker).where(Worker.worker_id == worker_id)
    result = await db.execute(stmt)
    worker = result.scalar_one_or_none()
    if not worker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Worker '{worker_id}' not found",
        )

    worker.status = WorkerStatus.DRAINING
    await db.commit()
    await db.refresh(worker)
    return WorkerResponse.model_validate(worker)


@router.delete(
    "/{worker_id}",
    status_code=status.HTTP_200_OK,
    summary="Deregister/remove a worker from fleet registry (Admin only)",
)
async def delete_worker(
    worker_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Deregister a dead or decommissioned worker node.
    """
    stmt = select(Worker).where(Worker.worker_id == worker_id)
    result = await db.execute(stmt)
    worker = result.scalar_one_or_none()
    if not worker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Worker '{worker_id}' not found",
        )

    await db.delete(worker)
    await db.commit()
    return {"success": True, "worker_id": worker_id}
