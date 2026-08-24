import io
import time
import uuid
import logging
import traceback
from datetime import datetime, timezone, timedelta
from contextlib import redirect_stdout, redirect_stderr
from typing import Optional, Dict, Any, Union, List
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import Job, JobExecution, DLQEntry, Queue, RetryPolicy, JobStatus, ExecutionStatus
from backend.app.core.ws_manager import ws_manager
from worker.app.tasks.registry import task_registry
from worker.app.engine.retry import RetryBackoffCalculator
from worker.app.engine.ai_diagnostics import AIDiagnosticEngine

import inspect
from worker.app.engine.context import ExecutionContext

logger = logging.getLogger("scheduler.runner")


class TaskRunner:
    """
    Executes a claimed job in a sandboxed runtime, intercepts stdout/stderr logs,
    measures millisecond execution time, records audit logs, evaluates DAG dependencies,
    and applies AI root cause analysis upon DLQ escalation.
    """

    @staticmethod
    async def execute_job(
        session: AsyncSession,
        job_or_id: Union[Job, uuid.UUID],
        worker_id: str,
        lease_token: Optional[uuid.UUID] = None,
    ) -> JobExecution:
        # Determine the specific lease token held by this worker instance
        held_lease_token = lease_token
        if held_lease_token is None and isinstance(job_or_id, Job):
            held_lease_token = job_or_id.lease_token

        # Load fresh job instance with queue & retry_policy
        job_id = job_or_id if isinstance(job_or_id, uuid.UUID) else job_or_id.id
        stmt = (
            select(Job)
            .options(selectinload(Job.queue).selectinload(Queue.retry_policy))
            .where(Job.id == job_id)
            .execution_options(populate_existing=True)
        )
        res = await session.execute(stmt)
        job = res.scalar_one()

        if held_lease_token is None:
            held_lease_token = job.lease_token

        log_buffer = io.StringIO()
        start_wall_time = datetime.now(timezone.utc)
        start_perf = time.perf_counter()
        execution_id = uuid.uuid4()

        context = ExecutionContext(
            execution_id=execution_id,
            job_id=job.id,
            queue_id=job.queue_id,
            job_name=job.name,
            attempt_number=job.attempt_count,
            max_retries=job.max_retries,
            idempotency_key=job.idempotency_key,
            lease_token=held_lease_token,
            worker_id=worker_id,
            db_session=session,
        )

        logger.info(
            f"▶️ [Worker {worker_id}] Executing Job '{job.name}' (ID: {job.id}, "
            f"Execution ID: {execution_id}, Lease: {held_lease_token}, Attempt: {job.attempt_count}/{job.max_retries})"
        )

        await ws_manager.broadcast("job_running", {
            "job_id": str(job.id),
            "name": job.name,
            "status": "running",
            "worker_id": worker_id,
            "attempt": job.attempt_count,
        })

        handler = task_registry.get(job.name)
        status_enum = ExecutionStatus.SUCCESS
        result_payload: Optional[Dict[str, Any]] = None
        error_msg: Optional[str] = None
        stack_trace_str: Optional[str] = None

        try:
            with redirect_stdout(log_buffer), redirect_stderr(log_buffer):
                # Inspect handler signature to support both (payload) and (payload, context)
                sig = inspect.signature(handler)
                if len(sig.parameters) >= 2 or "context" in sig.parameters or "ctx" in sig.parameters:
                    result_payload = await handler(job.payload, context)
                else:
                    result_payload = await handler(job.payload)
        except Exception as e:
            status_enum = ExecutionStatus.FAILED
            error_msg = str(e)
            stack_trace_str = traceback.format_exc()
            logger.warning(f"❌ [Worker {worker_id}] Job '{job.name}' ({job.id}) failed: {error_msg}")
        finally:
            end_perf = time.perf_counter()
            end_wall_time = datetime.now(timezone.utc)
            duration_ms = max(1, int((end_perf - start_perf) * 1000))
            logs_captured = log_buffer.getvalue()

        # Record execution audit log with explicit execution_id and attempt_number
        execution = JobExecution(
            id=execution_id,
            job_id=job.id,
            worker_id=worker_id,
            attempt_number=job.attempt_count,
            status=status_enum,
            started_at=start_wall_time,
            finished_at=end_wall_time,
            duration_ms=duration_ms,
            error_message=error_msg,
            stack_trace=stack_trace_str,
            logs=logs_captured or None,
        )
        session.add(execution)

        # 🛡️ Atomic Fenced Finalization with Lease Token
        if status_enum == ExecutionStatus.SUCCESS:
            finalize_stmt = (
                update(Job)
                .where(
                    Job.id == job.id,
                    Job.lease_token == context.lease_token,
                    Job.status == JobStatus.RUNNING,
                )
                .values(
                    status=JobStatus.COMPLETED,
                    result=result_payload,
                    completed_at=end_wall_time,
                    locked_by_worker_id=None,
                    lock_expires_at=None,
                    lease_token=None,
                    error_message=None,
                    updated_at=end_wall_time,
                )
            )
            finalize_res = await session.execute(finalize_stmt)
            if finalize_res.rowcount == 0:
                logger.warning(
                    f"⛔ [Fencing Token Mismatch] Worker '{worker_id}' lost lease for Job '{job.name}' (ID: {job.id}, "
                    f"Token: {context.lease_token}). Finalization rejected (Job was reclaimed by Reaper/another worker)."
                )
                execution.status = ExecutionStatus.KILLED
                execution.error_message = "Fenced: Worker lease expired during execution; finalization aborted."
                await session.commit()
                return execution

            logger.info(f"✅ [Worker {worker_id}] Job '{job.name}' ({job.id}) completed in {duration_ms}ms (Lease: {context.lease_token})")

            await ws_manager.broadcast("job_completed", {
                "job_id": str(job.id),
                "name": job.name,
                "status": "completed",
                "duration_ms": duration_ms,
                "worker_id": worker_id,
            })

            # ⛓️ DAG Workflow: Unlock dependent child jobs
            child_stmt = select(Job).where(
                Job.parent_job_id == job.id,
                Job.status == JobStatus.SCHEDULED,
            )
            child_res = await session.execute(child_stmt)
            children = child_res.scalars().all()
            for child in children:
                child.status = JobStatus.QUEUED
                child.run_at = end_wall_time
                child.updated_at = end_wall_time
                logger.info(f"⛓️ [DAG Engine] Unlocked downstream child Job '{child.name}' ({child.id})")
                await ws_manager.broadcast("job_queued", {
                    "job_id": str(child.id),
                    "name": child.name,
                    "status": "queued",
                })

        else:
            # Failure handling with lease fencing token protection
            if job.attempt_count < job.max_retries:
                retry_policy = job.queue.retry_policy if job.queue else None
                backoff_seconds = RetryBackoffCalculator.calculate_delay(
                    attempt_number=job.attempt_count,
                    policy=retry_policy,
                )
                finalize_stmt = (
                    update(Job)
                    .where(
                        Job.id == job.id,
                        Job.lease_token == context.lease_token,
                        Job.status == JobStatus.RUNNING,
                    )
                    .values(
                        status=JobStatus.SCHEDULED if backoff_seconds > 0 else JobStatus.QUEUED,
                        run_at=end_wall_time + timedelta(seconds=backoff_seconds),
                        locked_by_worker_id=None,
                        lock_expires_at=None,
                        lease_token=None,
                        error_message=error_msg,
                        updated_at=end_wall_time,
                    )
                )
                finalize_res = await session.execute(finalize_stmt)
                if finalize_res.rowcount == 0:
                    logger.warning(
                        f"⛔ [Fencing Token Mismatch] Worker '{worker_id}' lost lease for Job '{job.name}' (ID: {job.id}). "
                        f"Retry scheduling skipped because lease was reclaimed."
                    )
                    execution.status = ExecutionStatus.KILLED
                    execution.error_message = "Fenced: Worker lease expired during execution."
                    await session.commit()
                    return execution

                logger.info(
                    f"🔄 [Worker {worker_id}] Job '{job.name}' ({job.id}) scheduled for retry in {backoff_seconds}s (Attempt {job.attempt_count}/{job.max_retries})"
                )

                await ws_manager.broadcast("job_retrying", {
                    "job_id": str(job.id),
                    "name": job.name,
                    "status": "scheduled" if backoff_seconds > 0 else "queued",
                    "backoff_seconds": backoff_seconds,
                    "attempt": job.attempt_count,
                    "worker_id": worker_id,
                })
            else:
                finalize_stmt = (
                    update(Job)
                    .where(
                        Job.id == job.id,
                        Job.lease_token == context.lease_token,
                        Job.status == JobStatus.RUNNING,
                    )
                    .values(
                        status=JobStatus.DEAD_LETTER,
                        locked_by_worker_id=None,
                        lock_expires_at=None,
                        lease_token=None,
                        error_message=error_msg,
                        updated_at=end_wall_time,
                    )
                )
                finalize_res = await session.execute(finalize_stmt)
                if finalize_res.rowcount == 0:
                    logger.warning(
                        f"⛔ [Fencing Token Mismatch] Worker '{worker_id}' lost lease for Job '{job.name}' (ID: {job.id}). "
                        f"DLQ escalation skipped because lease was reclaimed."
                    )
                    execution.status = ExecutionStatus.KILLED
                    execution.error_message = "Fenced: Worker lease expired during execution."
                    await session.commit()
                    return execution

                logger.warning(f"💀 [Worker {worker_id}] Job '{job.name}' ({job.id}) moved to Dead Letter Queue")

                # 🧠 AI-Assisted Root Cause Diagnosis
                ai_summary = AIDiagnosticEngine.analyze_failure(
                    task_name=job.name,
                    error_message=error_msg,
                    stack_trace=stack_trace_str,
                    payload=job.payload,
                )

                dlq = DLQEntry(
                    job_id=job.id,
                    queue_id=job.queue_id,
                    failed_reason=f"Exhausted {job.max_retries} retry attempts. Last error: {error_msg}",
                    total_attempts=job.attempt_count,
                    last_error=stack_trace_str or error_msg,
                    ai_failure_summary=ai_summary,
                    moved_to_dlq_at=end_wall_time,
                )
                session.add(dlq)

                await ws_manager.broadcast("job_dead_letter", {
                    "job_id": str(job.id),
                    "name": job.name,
                    "status": "dead_letter",
                    "error": error_msg,
                    "worker_id": worker_id,
                })

                # ⛓️ DAG Workflow: Cancel dependent child jobs if parent died in DLQ
                child_stmt = select(Job).where(
                    Job.parent_job_id == job.id,
                    Job.status == JobStatus.SCHEDULED,
                )
                child_res = await session.execute(child_stmt)
                children = child_res.scalars().all()
                for child in children:
                    child.status = JobStatus.CANCELLED
                    child.error_message = f"Parent DAG Job ({job.id}) failed permanently and moved to DLQ."
                    child.updated_at = end_wall_time
                    logger.warning(f"⛓️ [DAG Engine] Cancelled child Job '{child.name}' ({child.id}) due to parent failure.")
                    await ws_manager.broadcast("job_cancelled", {
                        "job_id": str(child.id),
                        "name": child.name,
                        "status": "cancelled",
                    })

        await session.commit()
        return execution
