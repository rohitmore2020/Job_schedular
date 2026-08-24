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

---

## 7. Execution Semantics: At-Least-Once Execution & Side-Effect Idempotency

### The Distributed Systems Reality: Why "Exactly-Once" is a Myth
In distributed job processing, network partitions, out-of-memory crashes, and lease expirations make true end-to-end "exactly-once" execution across external side effects impossible:

```
Worker A claims Job
       ↓
Executes task & performs external side effect (e.g. Stripe charge, Email API)
       ↓
Worker A crashes (kernel panic / OOM / network disconnect) before acknowledging DB
       ↓
Lease expires in database (`lock_expires_at < NOW()`)
       ↓
Worker B claims and re-executes same Job (Attempt 2)
```

Without explicit application-level idempotency, the external side effect would be executed twice.

### Architectural Classification & Guarantee:
Our scheduler is architected and formally documented as:
> **At-Least-Once execution with idempotent job submission, lease-based recovery, and task-level side-effect idempotency.**

### How Idempotent Execution is Achieved:
1. **Execution Metadata & Context:**
   Every job execution receives a unique `execution_id` (UUID) and explicitly exposes `attempt_number` via `ExecutionContext`.
2. **Side-Effect Idempotency Pattern:**
   For tasks interacting with external third-party systems, handlers use the built-in database-backed idempotency mechanism:

```
job_id + operation_name
          ↓
Check `idempotency_records` (key: `job:<job_id>:op:<operation>`)
          ├── If found ('completed'): Skip external call & return cached result
          └── If not found:
                    ↓
              Execute external side effect
                    ↓
              Persist record in `idempotency_records`
                    ↓
              Return result
```

This guarantees that even when lease recovery triggers multiple execution attempts of a job, all external side effects execute **effectively once**.

---

## 8. Lease Fencing Tokens: Eliminating Split-Brain Zombie Worker State Corruption

### The Problem: Asynchronous Split-Brain Race
In any distributed lease-based system without fencing:
```
Worker A claims Job X (starts execution)
       ↓
Worker A loses network or suffers long GC pause (35s)
       ↓
Lease expires (`lock_expires_at < NOW()`)
       ↓
Lease Reaper reclaims Job X to `QUEUED`
       ↓
Worker B claims Job X (starts execution)
       ↓
Worker A unpauses and finishes old task
       ↓
Worker A attempts UPDATE jobs SET status = 'completed'
```
Without fencing, Worker A would blindly overwrite Worker B's active execution, prematurely mark the job complete with stale results, and unlock downstream DAG jobs before Worker B finishes!

### The Solution: Monotonic Fencing Lease Tokens
Every time a job is claimed, the database generates and assigns a unique `lease_token = UUID`:

```sql
UPDATE jobs
SET status = 'running',
    locked_by_worker_id = :worker_id,
    lease_token = :lease_token,
    lock_expires_at = NOW() + INTERVAL '30 seconds',
    attempt_count = attempt_count + 1
WHERE id = :job_id
RETURNING id, lease_token;
```

When any worker attempts to finalize completion, failure, or DLQ escalation, the SQL update strictly enforces the held lease token:

```sql
UPDATE jobs
SET status = 'completed',
    completed_at = NOW(),
    locked_by_worker_id = NULL,
    lease_token = NULL,
    lock_expires_at = NULL
WHERE id = :job_id
  AND lease_token = :held_lease_token
  AND status = 'running';
```

### Result:
- If Worker A was reclaimed by the Reaper and Worker B claimed Job X, the database row now holds `lease_token = Token_B`.
- Worker A's update with `Token_A` matches **0 rows** (`rowcount == 0`).
- Worker A's finalization is rejected and aborted (`ExecutionStatus.KILLED`).
- Worker B executes safely without interference or data corruption.

---

## 9. Scheduled & Recurring Jobs: Deterministic Logical Execution Keys

### The Distributed Cron Race
In high-availability deployments with multiple scheduler daemon replicas:
```
Scheduler Replica A               Scheduler Replica B
        │                                  │
        ├─── Evaluates `next_run_at <= NOW()` ───┤
        │                                  │
        ▼                                  ▼
Attempt to create Job             Attempt to create Job
        │                                  │
        └─── Double Execution Danger! ─────┘
```

### The Solution: Deterministic Logical Execution Keys
Every recurring job tick is stamped with a deterministic logical key derived from the schedule ID and logical execution fire time:
$$\text{idempotency\_key} = \text{"cron:"} + \text{schedule\_id} + \text{":"} + \text{scheduled\_for.isoformat()}$$

For example:
```
cron job #17 at 2026-08-23 18:00 UTC
        ↓
unique key: cron:17:2026-08-23T18:00:00+00:00
```

Coupled with PostgreSQL's partial unique index (`idx_jobs_idempotency` ON `(queue_id, idempotency_key)`), the database enforces that **only one occurrence can ever be created for that scheduled tick**. Any concurrent replica attempting to insert the same tick triggers `ON CONFLICT DO NOTHING` and gracefully skips creation without errors.

---

## 10. First-Class Batch Orchestration Subsystem

### What is a Batch?
Rather than an opaque single job whose JSON payload contains an array of tasks, a **Batch** is a dedicated first-class coordinator entity:

```
JobBatch (batch_id: UUID)
 ├── total_jobs: 100
 ├── completed_jobs: 75
 ├── failed_jobs: 3
 ├── pending_jobs: 22
 ├── progress_percent: 75.0%
 └── status: "processing"
      │
      ├── Child Job 1 (job_id: UUID, status: "completed")
      ├── Child Job 2 (job_id: UUID, status: "completed")
      ├── Child Job 3 (job_id: UUID, status: "dead_letter")
      └── Child Job N (job_id: UUID, status: "queued")
```

### Architectural Benefits
1. **Parallel Worker Distribution:** Every child job is an individual row in PostgreSQL claimed independently by competing workers across the fleet under `FOR UPDATE SKIP LOCKED`.
2. **Aggregated Live Progress:** The dashboard renders visual progress bars:
   `████████████░░░░ 75% | 75/100 completed, 3 failed, 22 running`
3. **Batch-Level Lifecycle APIs:**
   - `POST /api/v1/queues/{queue_id}/batches` (atomic creation of $N$ jobs)
   - `GET /api/v1/batches/{id}` (real-time progress querying)
   - `POST /api/v1/batches/{id}/cancel` (cancels all pending/queued child jobs)
   - `POST /api/v1/batches/{id}/retry` (re-enqueues failed/DLQ child jobs)

---

## 11. Handling the CLAIMED State: Atomic Transition (`QUEUED -> RUNNING`)

### Architectural Rationale
The scheduler uses an atomic database claim that acquires ownership and transitions the job directly from `QUEUED` to `RUNNING`. A persistent `CLAIMED` state is intentionally avoided because it would introduce an unnecessary intermediate state and additional recovery complexity.

```
┌──────────┐   Atomic Poll CTE (SKIP LOCKED)   ┌───────────┐   Runner Finished   ┌─────────────┐
│  QUEUED  │ ─────────────────────────────────> │  RUNNING  │ ──────────────────> │  COMPLETED  │
└──────────┘  - Sets status = 'running'         └───────────┘  - Status = 'completed' └─────────────┘
              - Assigns locked_by_worker_id                    - Releases lease
              - Stamps lease_token (UUID)
              - Sets lock_expires_at (NOW + 30s)
```

### Engineering Trade-Off Analysis
1. **Single-Transaction State Transition:** In PostgreSQL, combining row selection (`FOR UPDATE SKIP LOCKED`) and state update (`status = 'running'`) in a single CTE minimizes round-trips to the database and eliminates partial claim states.
2. **Elimination of Zombie Claim Recovery:** A separate persistent `CLAIMED` status would require a dedicated "claim timeout reaper" separate from the execution "lease reaper". By immediately stamping a lease token and setting `status = 'running'` with `lock_expires_at = NOW() + 30s`, the standard **Lease Reaper** and **Fencing Token Mechanism** manage all crash recovery seamlessly under one unified invariant.
3. **Compatibility:** `JobStatus.CLAIMED` remains in the schema enum for backwards compatibility and external integrations, while the internal high-performance worker engine utilizes the streamlined zero-overhead transition.

---

## 12. Worker Graceful Shutdown & In-Flight Draining (`SIGTERM` / `SIGINT`)

### Operational Challenge
In cloud environments (Kubernetes, Docker Swarm, rolling deployments), worker pods are frequently restarted, updated, or scaled down. Abruptly terminating workers results in interrupted jobs, wasted compute, and unnecessary lease timeouts.

### Graceful Shutdown Sequence
When a worker daemon receives a termination signal (`SIGTERM` or `SIGINT`), it initiates a zero-drop draining protocol:

```
Worker receives SIGTERM / SIGINT
       │
       ▼
1. Stop accepting new jobs
   • `is_running = False` immediately halts the queue polling loop.
   • Unclaimed jobs in `QUEUED` status are left untouched for healthy workers.
       │
       ▼
2. Heartbeat status = DRAINING
   • Sets `Worker.status = WorkerStatus.DRAINING` in the database.
   • Heartbeat emitter continues renewing in-flight job leases and broadcasting telemetry.
   • Dashboard displays yellow "DRAINING" badge for real-time operator visibility.
       │
       ▼
3. Finish active in-flight jobs
   • Daemon calls `await asyncio.gather(*self._active_tasks, return_exceptions=True)`.
   • Every in-flight task executes to completion and records audit logs and output payloads.
       │
       ▼
4. Stop heartbeat emitter & release resources
   • Heartbeat background task cancelled.
       │
       ▼
5. Exit
   • Sets `Worker.status = WorkerStatus.DEAD` in database.
   • Process exits cleanly with exit code 0.
```

### Guarantees
1. **Zero Aborted Tasks:** Jobs currently being processed are guaranteed to finish before the process terminates.
2. **Zero Orphaned Claims:** No new jobs are claimed once the shutdown signal is received.
3. **Immediate Operator Observability:** The cluster immediately distinguishes between a dying worker (`DRAINING`) and a hard-crashed worker (`DEAD`).






