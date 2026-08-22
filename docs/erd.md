# Database Schema & Entity Relationship Diagram (ERD)

## 1. Entity Relationship Diagram (Mermaid)

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ USERS : "has many"
    ORGANIZATIONS ||--o{ PROJECTS : "owns"
    PROJECTS ||--o{ QUEUES : "manages"
    PROJECTS ||--o{ PROJECT_API_KEYS : "authenticates"
    PROJECTS ||--o{ SCHEDULED_JOBS : "schedules"
    QUEUES ||--o{ JOBS : "enqueues"
    QUEUES ||--o| RETRY_POLICIES : "configures"
    QUEUES ||--o{ SCHEDULED_JOBS : "targets"
    QUEUES ||--o{ DLQ_ENTRIES : "isolates"
    JOBS ||--o{ JOB_EXECUTIONS : "records"
    JOBS ||--o| DLQ_ENTRIES : "escalates to"
    JOBS ||--o{ JOBS : "parent_job_id (DAG)"
    WORKERS ||--o{ WORKER_HEARTBEATS : "telemetry"

    ORGANIZATIONS {
        uuid id PK
        string name
        string slug UK
        datetime created_at
        datetime updated_at
    }

    USERS {
        uuid id PK
        uuid org_id FK
        string email UK
        string hashed_password
        string full_name
        enum role "admin, member"
        datetime created_at
        datetime updated_at
    }

    PROJECTS {
        uuid id PK
        uuid org_id FK
        string name
        string slug UK
        text description
        datetime created_at
        datetime updated_at
    }

    QUEUES {
        uuid id PK
        uuid project_id FK
        string name
        int priority
        int concurrency_limit
        int rate_limit_rps
        boolean is_paused
        datetime created_at
        datetime updated_at
    }

    RETRY_POLICIES {
        uuid id PK
        uuid queue_id FK, UK
        enum strategy "fixed, linear, exponential"
        int max_retries
        int initial_interval_sec
        int max_interval_sec
        float backoff_multiplier
        boolean jitter
    }

    JOBS {
        uuid id PK
        uuid queue_id FK
        string idempotency_key
        string name
        enum status "queued, running, completed, failed, dead_letter, scheduled, cancelled"
        int priority
        jsonb payload
        jsonb result
        text error_message
        int attempt_count
        int max_retries
        datetime run_at
        datetime claimed_at
        datetime started_at
        datetime completed_at
        string locked_by_worker_id
        datetime lock_expires_at
        uuid parent_job_id FK
        jsonb tags
        datetime created_at
        datetime updated_at
    }

    JOB_EXECUTIONS {
        uuid id PK
        uuid job_id FK
        string worker_id
        int attempt_number
        enum status "success, failed"
        datetime started_at
        datetime finished_at
        int duration_ms
        text error_message
        text stack_trace
        text logs
    }

    DLQ_ENTRIES {
        uuid id PK
        uuid job_id FK, UK
        uuid queue_id FK
        text failed_reason
        int total_attempts
        text last_error
        text ai_failure_summary
        datetime moved_to_dlq_at
        boolean is_replayed
        datetime replayed_at
    }

    SCHEDULED_JOBS {
        uuid id PK
        uuid project_id FK
        uuid queue_id FK
        string name
        string cron_expression
        string timezone
        jsonb payload
        int priority
        boolean is_active
        datetime last_run_at
        datetime next_run_at
        int total_runs_count
        datetime created_at
        datetime updated_at
    }

    WORKERS {
        string worker_id PK
        string hostname
        int pid
        int concurrency_limit
        int current_active_jobs
        enum status "alive, dead, paused"
        jsonb assigned_queues
        datetime started_at
        datetime last_heartbeat_at
    }

    WORKER_HEARTBEATS {
        uuid id PK
        string worker_id FK
        float cpu_percent
        float memory_mb
        int active_jobs
        datetime timestamp
    }
```

---

## 2. Partial Performance Indexes

1. **`idx_jobs_claim_ready`**:
   - `ON jobs (queue_id, priority DESC, run_at ASC) WHERE status = 'queued'`
   - Accelerates `FOR UPDATE SKIP LOCKED` atomic worker claims to sub-millisecond lookups.
2. **`idx_jobs_running_lease`**:
   - `ON jobs (lock_expires_at) WHERE status = 'running'`
   - Enables instant zombie reaper detection of expired leases without scanning completed jobs.
3. **`idx_jobs_idempotency`**:
   - `ON jobs (queue_id, idempotency_key) UNIQUE WHERE idempotency_key IS NOT NULL`
   - Guarantees zero-duplicate job insertion on concurrent client retries.
