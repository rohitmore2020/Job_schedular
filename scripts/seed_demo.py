import sys
import os
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import asyncio
import uuid
import hashlib
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from rich.console import Console

from backend.app.core.database import AsyncSessionLocal
from backend.app.core.security import hash_password
from backend.app.models import (
    Organization,
    User,
    Project,
    ProjectAPIKey,
    Queue,
    RetryPolicy,
    Job,
    JobExecution,
    ScheduledJob,
    DLQEntry,
    Worker,
    WorkerHeartbeat,
    UserRole,
    JobStatus,
    RetryStrategy,
    WorkerStatus,
    ExecutionStatus,
)

console = Console()


async def seed_database():
    console.print("🌱 [bold green]Starting Database Seeding...[/bold green]")
    async with AsyncSessionLocal() as session:
        # Check if already seeded
        existing_org = await session.scalar(select(Organization).where(Organization.slug == "acme-corp"))
        if existing_org:
            console.print("ℹ️  [bold yellow]Database is already seeded. Skipping.[/bold yellow]")
            return

        # 1. Organization
        org = Organization(
            name="Acme Corporation",
            slug="acme-corp",
        )
        session.add(org)
        await session.flush()

        # 2. Users
        admin_user = User(
            org_id=org.id,
            email="admin@distributed-scheduler.io",
            hashed_password=hash_password("Password123!"),
            full_name="Lead Platform Engineer",
            role=UserRole.ADMIN,
        )
        acme_admin = User(
            org_id=org.id,
            email="admin@acme.com",
            hashed_password=hash_password("admin123"),
            full_name="Admin Engineer",
            role=UserRole.ADMIN,
        )
        member_user = User(
            org_id=org.id,
            email="dev@acme.com",
            hashed_password=hash_password("dev123"),
            full_name="Staff Developer",
            role=UserRole.MEMBER,
        )
        session.add_all([admin_user, acme_admin, member_user])
        await session.flush()

        # 3. Projects
        prod_project = Project(
            org_id=org.id,
            name="Production Services",
            slug="prod-services",
            description="Core asynchronous processing queues and business tasks",
        )
        analytics_project = Project(
            org_id=org.id,
            name="Analytics & ETL",
            slug="analytics-etl",
            description="Batch report generation and machine learning pipelines",
        )
        session.add_all([prod_project, analytics_project])
        await session.flush()

        # 4. Project API Key
        raw_key = "cjs_live_acme_secret_token_998877"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        api_key = ProjectAPIKey(
            project_id=prod_project.id,
            name="Production Backend API Key",
            key_hash=key_hash,
            prefix="cjs_live_acme...",
        )
        session.add(api_key)

        # 5. Queues & Retry Policies
        queue_emails = Queue(
            project_id=prod_project.id,
            name="transactional-emails",
            priority=50,
            concurrency_limit=5,
            rate_limit_rps=20,
            is_paused=False,
        )
        queue_video = Queue(
            project_id=prod_project.id,
            name="video-transcoder",
            priority=20,
            concurrency_limit=2,
            is_paused=False,
        )
        queue_reports = Queue(
            project_id=analytics_project.id,
            name="nightly-reports",
            priority=10,
            concurrency_limit=3,
            is_paused=False,
        )
        session.add_all([queue_emails, queue_video, queue_reports])
        await session.flush()

        # Retry Policies
        retry_email = RetryPolicy(
            queue_id=queue_emails.id,
            strategy=RetryStrategy.EXPONENTIAL,
            max_retries=3,
            initial_interval_sec=5,
            max_interval_sec=300,
            backoff_multiplier=2.0,
            jitter=True,
        )
        retry_video = RetryPolicy(
            queue_id=queue_video.id,
            strategy=RetryStrategy.LINEAR,
            max_retries=2,
            initial_interval_sec=10,
            max_interval_sec=600,
            backoff_multiplier=1.0,
            jitter=False,
        )
        session.add_all([retry_email, retry_video])
        await session.flush()

        # 6. Sample Jobs in Various States
        for i in range(1, 6):
            job = Job(
                queue_id=queue_emails.id,
                name="send_welcome_email",
                status=JobStatus.QUEUED,
                priority=10 + i * 5,
                payload={"user_id": f"usr_{1000+i}", "template": "welcome_v2", "email": f"user{i}@example.com"},
                idempotency_key=f"welcome-email-user-{1000+i}",
                tags=["email", "onboarding"],
            )
            session.add(job)

        # Scheduled (delayed) jobs
        now_utc = datetime.now(timezone.utc)
        delayed_job = Job(
            queue_id=queue_emails.id,
            name="send_trial_ending_reminder",
            status=JobStatus.SCHEDULED,
            priority=15,
            payload={"user_id": "usr_999", "days_left": 3},
            run_at=now_utc + timedelta(hours=2),
            tags=["email", "billing"],
        )
        session.add(delayed_job)
        await session.flush()

        # Completed Job with Execution Log
        comp_job = Job(
            queue_id=queue_emails.id,
            name="send_invoice_receipt",
            status=JobStatus.COMPLETED,
            priority=30,
            payload={"invoice_id": "inv_8877", "amount_usd": 149.00},
            result={"status": "delivered", "message_id": "msg_aws_ses_12345", "duration_ms": 240},
            started_at=now_utc - timedelta(minutes=5),
            completed_at=now_utc - timedelta(minutes=5) + timedelta(milliseconds=240),
            attempt_count=1,
            tags=["email", "billing", "receipt"],
        )
        session.add(comp_job)
        await session.flush()

        execution_log = JobExecution(
            job_id=comp_job.id,
            worker_id="worker-node-alpha-1",
            attempt_number=1,
            status=ExecutionStatus.SUCCESS,
            started_at=comp_job.started_at,
            finished_at=comp_job.completed_at,
            duration_ms=240,
            logs="[INFO] Connecting to SES SMTP gateway...\n[INFO] Message sent successfully. ID: msg_aws_ses_12345",
        )
        session.add(execution_log)

        # Dead Letter Queue Job with Stack Trace
        dlq_job = Job(
            queue_id=queue_video.id,
            name="transcode_4k_stream",
            status=JobStatus.DEAD_LETTER,
            priority=20,
            payload={"video_url": "https://s3.amazonaws.com/media/raw_clip_4k.mp4", "codec": "h265"},
            error_message="Fatal: FFmpeg exit code 137 (Out of memory)",
            attempt_count=3,
            max_retries=2,
            tags=["transcode", "video"],
        )
        session.add(dlq_job)
        await session.flush()

        dlq_entry = DLQEntry(
            job_id=dlq_job.id,
            queue_id=queue_video.id,
            failed_reason="Exceeded maximum retry limit (2 retries exhausted)",
            total_attempts=3,
            last_error="Command '['ffmpeg', '-i', 'raw_clip_4k.mp4', '-vcodec', 'libx265']' killed by signal 9 (SIGKILL)",
            ai_failure_summary="FFmpeg worker process was killed due to memory exhaustion (OOM). Recommended Action: Increase worker container RAM to 4GB or configure chunked transcoding.",
        )
        session.add(dlq_entry)

        # 7. Scheduled (Cron) Jobs
        cron_job_1 = ScheduledJob(
            project_id=prod_project.id,
            queue_id=queue_emails.id,
            name="Hourly System Digest",
            cron_expression="0 * * * *",
            payload={"digest_type": "hourly_stats"},
            next_run_at=now_utc + timedelta(minutes=45),
        )
        cron_job_2 = ScheduledJob(
            project_id=analytics_project.id,
            queue_id=queue_reports.id,
            name="Daily Executive Summary Report",
            cron_expression="0 6 * * *",
            payload={"report": "executive_summary_daily"},
            next_run_at=now_utc + timedelta(hours=12),
        )
        session.add_all([cron_job_1, cron_job_2])

        # 8. Active Workers & Heartbeats
        worker_1 = Worker(
            worker_id="worker-node-alpha-1",
            hostname="worker-prod-az1.internal",
            pid=4812,
            concurrency_limit=5,
            current_active_jobs=1,
            status=WorkerStatus.ALIVE,
            assigned_queues=["transactional-emails", "nightly-reports"],
            started_at=now_utc - timedelta(hours=3),
            last_heartbeat_at=now_utc,
        )
        worker_2 = Worker(
            worker_id="worker-node-beta-2",
            hostname="worker-prod-az2.internal",
            pid=4933,
            concurrency_limit=5,
            current_active_jobs=0,
            status=WorkerStatus.ALIVE,
            assigned_queues=["video-transcoder"],
            started_at=now_utc - timedelta(hours=1),
            last_heartbeat_at=now_utc,
        )
        session.add_all([worker_1, worker_2])
        await session.flush()

        hb_1 = WorkerHeartbeat(
            worker_id=worker_1.worker_id,
            cpu_percent=14.2,
            memory_mb=218.5,
            active_jobs=1,
            timestamp=now_utc,
        )
        hb_2 = WorkerHeartbeat(
            worker_id=worker_2.worker_id,
            cpu_percent=4.8,
            memory_mb=182.0,
            active_jobs=0,
            timestamp=now_utc,
        )
        session.add_all([hb_1, hb_2])

        await session.commit()
        console.print("✨ [bold green]Database successfully seeded with realistic demo data![/bold green]")
        console.print(f"👤 Admin User: [cyan]admin@distributed-scheduler.io[/cyan] (Password: [cyan]Password123![/cyan])")
        console.print(f"🔑 Demo Project API Key: [yellow]{raw_key}[/yellow]")


if __name__ == "__main__":
    asyncio.run(seed_database())
