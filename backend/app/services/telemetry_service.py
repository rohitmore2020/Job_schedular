import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from sqlalchemy import select, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import (
    User,
    Project,
    Queue,
    Job,
    JobExecution,
    Worker,
    WorkerHeartbeat,
    WorkerStatus,
    JobStatus,
    ExecutionStatus,
)
from backend.app.schemas.telemetry import (
    SystemTelemetry,
    QueueTelemetry,
    WorkerFleetTelemetry,
    FullTelemetryResponse,
)


class TelemetryService:
    @staticmethod
    async def get_telemetry(
        db: AsyncSession,
        user: User,
        project_id: Optional[uuid.UUID] = None,
    ) -> FullTelemetryResponse:
        now_utc = datetime.now(timezone.utc)
        one_min_ago = now_utc - timedelta(seconds=60)
        thirty_sec_ago = now_utc - timedelta(seconds=30)

        # 1. Base Query Filtered by Org / Project
        base_job_filter = [Project.org_id == user.org_id]
        if project_id:
            base_job_filter.append(Project.id == project_id)

        # System Job Metrics Aggregation
        job_stmt = (
            select(
                func.count(Job.id).label("total"),
                func.count(case((Job.status == JobStatus.QUEUED, 1))).label("queued"),
                func.count(case((Job.status == JobStatus.RUNNING, 1))).label("running"),
                func.count(case((Job.status == JobStatus.COMPLETED, 1))).label("completed"),
                func.count(case((Job.status == JobStatus.FAILED, 1))).label("failed"),
                func.count(case((Job.status == JobStatus.DEAD_LETTER, 1))).label("dead_letter"),
                func.count(case((Job.status == JobStatus.CANCELLED, 1))).label("cancelled"),
                func.count(case(((Job.status == JobStatus.COMPLETED) & (Job.completed_at >= one_min_ago), 1))).label("recent_completions"),
                func.count(case((Job.attempt_count > 1, 1))).label("retried_jobs"),
            )
            .join(Queue, Job.queue_id == Queue.id)
            .join(Project, Queue.project_id == Project.id)
            .where(and_(*base_job_filter))
        )
        job_res = await db.execute(job_stmt)
        job_row = job_res.fetchone()

        total_jobs = job_row[0] or 0
        queued_jobs = job_row[1] or 0
        running_jobs = job_row[2] or 0
        completed_jobs = job_row[3] or 0
        failed_jobs = job_row[4] or 0
        dead_letter_jobs = job_row[5] or 0
        cancelled_jobs = job_row[6] or 0
        recent_completions = job_row[7] or 0
        retried_jobs = job_row[8] or 0

        attempted_total = completed_jobs + failed_jobs + dead_letter_jobs
        success_rate = round((completed_jobs / max(1, attempted_total)) * 100.0, 1) if attempted_total > 0 else 100.0
        failure_rate = round(((failed_jobs + dead_letter_jobs) / max(1, attempted_total)) * 100.0, 1) if attempted_total > 0 else 0.0
        retry_rate = round((retried_jobs / max(1, total_jobs)) * 100.0, 1) if total_jobs > 0 else 0.0
        dlq_rate = round((dead_letter_jobs / max(1, total_jobs)) * 100.0, 1) if total_jobs > 0 else 0.0
        jobs_per_sec = round(recent_completions / 60.0, 2)

        system_telemetry = SystemTelemetry(
            total_jobs=total_jobs,
            queued_jobs=queued_jobs,
            running_jobs=running_jobs,
            completed_jobs=completed_jobs,
            failed_jobs=failed_jobs,
            dead_letter_jobs=dead_letter_jobs,
            cancelled_jobs=cancelled_jobs,
            jobs_per_sec=jobs_per_sec,
            success_rate_percent=success_rate,
            failure_rate_percent=failure_rate,
            retry_rate_percent=retry_rate,
            dlq_rate_percent=dlq_rate,
        )

        # 2. Worker Fleet Telemetry
        worker_stmt = select(Worker)
        worker_res = await db.execute(worker_stmt)
        workers = worker_res.scalars().all()

        online_workers = [w for w in workers if w.status == WorkerStatus.ALIVE and w.last_heartbeat_at >= thirty_sec_ago]
        busy_workers = [w for w in online_workers if w.current_active_jobs > 0]
        idle_workers = [w for w in online_workers if w.current_active_jobs == 0]
        total_active_jobs = sum(w.current_active_jobs for w in online_workers)

        # Latest average telemetry metrics
        hb_stmt = (
            select(
                func.avg(WorkerHeartbeat.cpu_percent).label("avg_cpu"),
                func.avg(WorkerHeartbeat.memory_mb).label("avg_ram"),
            )
            .where(WorkerHeartbeat.timestamp >= one_min_ago)
        )
        hb_res = await db.execute(hb_stmt)
        hb_row = hb_res.fetchone()
        avg_cpu = round(float(hb_row[0] or 0.0), 1)
        avg_ram = round(float(hb_row[1] or 0.0), 1)

        fleet_telemetry = WorkerFleetTelemetry(
            workers_online=len(online_workers),
            workers_busy=len(busy_workers),
            workers_idle=len(idle_workers),
            total_active_jobs=total_active_jobs,
            average_cpu_percent=avg_cpu,
            average_memory_mb=avg_ram,
        )

        # 3. Queues Observability Breakdown
        queue_filter = [Project.org_id == user.org_id]
        if project_id:
            queue_filter.append(Project.id == project_id)

        q_stmt = (
            select(Queue)
            .join(Project, Queue.project_id == Project.id)
            .where(and_(*queue_filter))
            .order_by(Queue.priority.desc())
        )
        q_res = await db.execute(q_stmt)
        queues = q_res.scalars().all()

        queue_telemetries = []
        for q in queues:
            # Aggregate per-queue metrics
            q_metrics_stmt = select(
                func.count(case((Job.status == JobStatus.QUEUED, 1))).label("depth"),
                func.count(case((Job.status == JobStatus.RUNNING, 1))).label("running"),
                func.count(case((Job.status == JobStatus.COMPLETED, 1))).label("completed"),
                func.count(case((Job.status == JobStatus.FAILED, 1))).label("failed"),
                func.count(case((Job.status == JobStatus.DEAD_LETTER, 1))).label("dead_letter"),
                func.min(case((Job.status == JobStatus.QUEUED, Job.created_at))).label("oldest_created"),
                func.count(case(((Job.status == JobStatus.COMPLETED) & (Job.completed_at >= one_min_ago), 1))).label("recent_completed"),
                func.avg(
                    case(
                        (Job.started_at.isnot(None), func.extract("epoch", Job.started_at) - func.extract("epoch", Job.created_at)),
                    )
                ).label("avg_wait_sec"),
            ).where(Job.queue_id == q.id)

            qm_res = await db.execute(q_metrics_stmt)
            qm_row = qm_res.fetchone()

            q_depth = qm_row[0] or 0
            q_running = qm_row[1] or 0
            q_completed = qm_row[2] or 0
            q_failed = qm_row[3] or 0
            q_dlq = qm_row[4] or 0
            q_oldest_created = qm_row[5]
            q_recent_completed = qm_row[6] or 0
            q_avg_wait_sec = qm_row[7]

            oldest_age = None
            if q_oldest_created:
                oldest_age = max(0.0, round((now_utc - q_oldest_created).total_seconds(), 1))

            avg_wait_ms = None
            if q_avg_wait_sec is not None and q_avg_wait_sec >= 0:
                avg_wait_ms = round(float(q_avg_wait_sec) * 1000.0, 1)

            utilization = round((q_running / max(1, q.concurrency_limit)) * 100.0, 1)
            q_tps = round(q_recent_completed / 60.0, 2)

            queue_telemetries.append(
                QueueTelemetry(
                    queue_id=q.id,
                    queue_name=q.name,
                    priority=q.priority,
                    concurrency_limit=q.concurrency_limit,
                    is_paused=q.is_paused,
                    queue_depth=q_depth,
                    running_jobs=q_running,
                    completed_jobs=q_completed,
                    failed_jobs=q_failed,
                    dead_letter_jobs=q_dlq,
                    concurrency_utilization_percent=min(100.0, utilization),
                    oldest_job_age_seconds=oldest_age,
                    average_wait_time_ms=avg_wait_ms,
                    throughput_jobs_per_sec=q_tps,
                )
            )

        return FullTelemetryResponse(
            system=system_telemetry,
            fleet=fleet_telemetry,
            queues=queue_telemetries,
            timestamp=now_utc.isoformat(),
        )
