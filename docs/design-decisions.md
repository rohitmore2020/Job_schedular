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


