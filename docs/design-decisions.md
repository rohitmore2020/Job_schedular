# Architectural Trade-Offs & Design Decisions

This document details the engineering trade-offs, design rationale, and technical considerations behind the **Codity Distributed Job Scheduler**.

---

## 1. Primary Engine: PostgreSQL (`FOR UPDATE SKIP LOCKED`) vs. Redis / RabbitMQ / Kafka

| Metric | PostgreSQL + SKIP LOCKED | Redis (e.g. BullMQ / Celery) | RabbitMQ / Kafka |
|---|---|---|---|
| **ACID Durability** | **Extreme (WAL + fsync)** | Memory-first; data loss risk on un-synced crashes | High (Disk log persistence) |
| **Transaction Atomicity** | **Atomic (Enqueue within business DB transaction)** | Requires 2-phase commit or dual-write | Requires Outbox pattern |
| **Queryability & Auditing** | **Instant SQL queries on payload, state & history** | Limited; keys evict or require secondary store | Requires stream consumers + DB sink |
| **Operational Complexity** | **Zero extra infrastructure (uses existing DB)** | Adds Redis cluster to maintain | High operational overhead |
| **Throughput Ceiling** | **15,000 – 40,000 jobs/sec per primary node** | 100,000+ jobs/sec in memory | 1,000,000+ msgs/sec |

### Decision:
We chose **PostgreSQL with `FOR UPDATE SKIP LOCKED` and partial indexes**. For 99% of business workloads (e-commerce, video processing, report generation, webhooks), ACID guarantees, transaction atomicity with business data, and zero infrastructure sprawl outweigh raw in-memory message counts.

---

## 2. Claiming Paradigm: Polling CTE vs. Listen/Notify

- **PostgreSQL `LISTEN / NOTIFY`:**
  - Fast wakeup on insert, but payload size is capped at 8000 bytes and does not work if worker is disconnected.
- **`FOR UPDATE SKIP LOCKED` with Adaptive Polling:**
  - Deterministic priority ordering (`priority DESC, run_at ASC`).
  - Workers use adaptive sleep (e.g. 100ms when queue is busy, backing off to 1.5s when idle) plus instantaneous WebSocket dispatch triggers.

---

## 3. Worker Concurrency: Asynchronous `asyncio.Semaphore` vs. Multi-Processing

- Each worker daemon runs on Python 3.11+ `asyncio` event loops managing a configurable `asyncio.Semaphore(concurrency_limit)`.
- For CPU-bound workloads (e.g. image/video processing), external binaries (`ffmpeg`, `cwebp`) or thread pool executors are invoked asynchronously without blocking the event loop.

---

## 4. Lease Timeouts & Heartbeat Renewals

- **Problem:** If a worker crashes mid-execution (OOM, power outage), the job must not hang in `running` status forever.
- **Solution:**
  - In-flight jobs are stamped with `lock_expires_at = NOW() + 30s`.
  - The worker background loop renews in-flight leases every 5s.
  - If a worker dies, the lease naturally expires, and the **Lease Reaper** reclaims the job within 10s back to `'queued'` status or routes to DLQ.

---

## 5. Retry Backoff: Full Jitter vs. Equal Jitter / Fixed

- Standard exponential backoff causes **"thundering herds"** when a downstream service recovers, as retrying workers all hit the API at the exact same second.
- We implemented AWS **Full Jitter**:
  $$\text{Delay} = \text{random}(0, \min(\text{max\_interval}, \text{initial\_interval} \times \text{multiplier}^{\text{attempt}}))$$
- Full Jitter guarantees an even distribution of retries over time, maximizing downstream recovery success.

---

## 6. DAG Workflows: Database-Driven Dependency Resolution

- We avoided complex external workflow engines (like Temporal / Airflow) in favor of declarative `parent_job_id` chaining.
- Child jobs stay in `SCHEDULED` status with `run_at = datetime.max`.
- When the parent job successfully transitions to `COMPLETED`, the worker runner atomically unblocks all child jobs to `QUEUED` with `run_at = NOW()`.
- If the parent dies permanently in DLQ, dependent child jobs are automatically cascade-cancelled.
