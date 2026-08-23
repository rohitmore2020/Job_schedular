import sys
import os
sys.path.insert(0, os.path.abspath("."))

import asyncio
import time
import uuid
import statistics
from datetime import datetime, timezone
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from backend.app.core.config import settings
from backend.app.models import Organization, Project, Queue, Job, JobExecution, JobStatus, ExecutionStatus
from worker.app.engine.claimer import AtomicClaimer
from worker.app.engine.runner import TaskRunner
from worker.app.tasks.registry import task_registry

# Register an instant zero-sleep handler for benchmarking raw scheduler throughput
@task_registry.register("benchmark_nop_task")
async def benchmark_nop_task(payload):
    return {"status": "ok", "processed_at": time.time()}

# NullPool Engine to handle high parallel worker concurrency cleanly
bench_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, echo=False)
BenchSessionLocal = async_sessionmaker(bind=bench_engine, class_=AsyncSession, expire_on_commit=False)


async def setup_benchmark_env():
    async with BenchSessionLocal() as session:
        org = Organization(name="Bench Org", slug=f"bench-org-{uuid.uuid4().hex[:6]}")
        session.add(org)
        await session.flush()

        proj = Project(org_id=org.id, name="Bench Proj", slug=f"bench-p-{uuid.uuid4().hex[:6]}")
        session.add(proj)
        await session.flush()

        queue = Queue(
            project_id=proj.id,
            name=f"bench-q-{uuid.uuid4().hex[:6]}",
            priority=50,
            concurrency_limit=100,
            is_paused=False,
        )
        session.add(queue)
        await session.commit()
        await session.refresh(queue)
        return queue


async def run_benchmark_matrix(job_count: int, worker_count: int):
    queue = await setup_benchmark_env()
    queue_name = queue.name
    queue_id = queue.id

    # 1. Ingest batch of jobs
    async with BenchSessionLocal() as session:
        now_utc = datetime.now(timezone.utc)
        for i in range(job_count):
            job = Job(
                queue_id=queue_id,
                name="benchmark_nop_task",
                status=JobStatus.QUEUED,
                payload={"index": i, "duration": 0.0},
                run_at=now_utc,
            )
            session.add(job)
        await session.commit()

    latencies = []
    failures = 0

    # 2. Worker loop
    async def worker_loop(worker_id: str):
        nonlocal failures
        consecutive_nones = 0
        while True:
            t0 = time.perf_counter()
            async with BenchSessionLocal() as session:
                job = await AtomicClaimer.claim_next_job(
                    session, worker_id=worker_id, assigned_queues=[queue_name]
                )
                if not job:
                    consecutive_nones += 1
                    rem = await session.scalar(
                        select(func.count(Job.id)).where(Job.queue_id == queue_id, Job.status == JobStatus.QUEUED)
                    )
                    if rem == 0 or consecutive_nones > 5:
                        break
                    await asyncio.sleep(0.002)
                    continue

                consecutive_nones = 0
                exec_res = await TaskRunner.execute_job(session, job, worker_id)
                t1 = time.perf_counter()
                elapsed_ms = (t1 - t0) * 1000.0
                latencies.append(elapsed_ms)

                if exec_res.status != ExecutionStatus.SUCCESS:
                    failures += 1

    # 3. Timed execution across worker fleet
    start_time = time.perf_counter()
    worker_tasks = [worker_loop(f"bench-worker-{w}") for w in range(worker_count)]
    await asyncio.gather(*worker_tasks)
    total_time = time.perf_counter() - start_time

    # 4. Check duplicate executions in database
    async with BenchSessionLocal() as session:
        dup_query = select(
            JobExecution.job_id,
            func.count(JobExecution.id).label("exec_count"),
        ).join(Job, JobExecution.job_id == Job.id).where(Job.queue_id == queue_id).group_by(JobExecution.job_id).having(func.count(JobExecution.id) > 1)
        dup_res = await session.execute(dup_query)
        duplicates = len(dup_res.fetchall())

    throughput = round(job_count / total_time, 2)
    if latencies:
        avg_latency = round(statistics.mean(latencies), 2)
        sorted_lats = sorted(latencies)
        p95_idx = int(0.95 * len(sorted_lats))
        p95_latency = round(sorted_lats[min(p95_idx, len(sorted_lats) - 1)], 2)
    else:
        avg_latency = 0.0
        p95_latency = 0.0

    print(
        f"| {job_count:4d} | {worker_count:2d} | {throughput:8.1f} ops/s | {avg_latency:6.1f} ms | {p95_latency:6.1f} ms | {failures:1d} failures | {duplicates:1d} duplicates |",
        flush=True
    )

    return {
        "job_count": job_count,
        "worker_count": worker_count,
        "throughput": throughput,
        "avg_latency": avg_latency,
        "p95_latency": p95_latency,
        "failures": failures,
        "duplicates": duplicates,
    }


async def main():
    print("\n## ⚡ Baseline Performance Benchmark Results", flush=True)
    print("\n| Jobs | Workers | Throughput | Avg Latency | P95 Latency | Failures | Duplicate Claims |", flush=True)
    print("| :---: | :---: | :---: | :---: | :---: | :---: | :---: |", flush=True)

    job_sizes = [100, 500, 1000]
    worker_counts = [1, 2, 5, 10]

    all_results = []
    for jobs in job_sizes:
        for workers in worker_counts:
            res = await run_benchmark_matrix(jobs, workers)
            all_results.append(res)

    print("\nFinished all 12 benchmark matrices successfully.", flush=True)

    import json
    with open("docs/benchmark_data.json", "w") as f:
        json.dump(all_results, f, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
