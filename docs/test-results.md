# 🧪 Test Execution & Baseline Performance Benchmark Report

**Project:** Codity Distributed Job Scheduler Platform  
**Environment:** Python 3.11.14 / PostgreSQL 16 (ACID `FOR UPDATE SKIP LOCKED`)  
**Date:** August 2026  

---

## 0.2 Automated Test & Coverage Results

### 📊 Summary
- **Total tests:** 65
- **Passed:** 65
- **Failed:** 0
- **Skipped:** 0
- **Coverage:** 69%

```
======================== 65 passed, 1 warning in 35.60s ========================
```

### 📋 Test Suite Breakdown

| Test File | Scenarios Tested | Passed | Status |
| :--- | :--- | :---: | :---: |
| `tests/test_day1_setup.py` | DB connectivity, `/health`, `/` root endpoint | 3/3 | ✅ PASSED |
| `tests/test_day2_models.py` | Org/Project/User hierarchy, queue retry policy, idempotency constraints, job execution lifecycle | 5/5 | ✅ PASSED |
| `tests/test_day4_auth.py` | Signup, duplicate email prevention, password hashing, JWT refresh rotation, `/me` auth guards | 5/5 | ✅ PASSED |
| `tests/test_day5_projects_queues.py` | Project CRUD, tenant isolation, API key generation, queue pause/resume | 3/3 | ✅ PASSED |
| `tests/test_day6_jobs.py` | Immediate & delayed scheduling, idempotency deduplication, race deduplication, batch submission, filtering & pagination, cancel/retry | 7/7 | ✅ PASSED |
| `tests/test_day7_worker_concurrency.py` | Atomic SKIP LOCKED claiming, multi-worker racing, concurrency caps, paused queue bypass, failure tracebacks | 6/6 | ✅ PASSED |
| `tests/test_day8_heartbeat_reaper.py` | Telemetry heartbeats, dead worker detection, lease reaper recovery, split-brain lease fencing, worker REST API | 5/5 | ✅ PASSED |
| `tests/test_day9_retry_dlq.py` | Exponential & jitter backoff algorithms, scheduled retry execution, DLQ escalation & 1-click redrive replay | 3/3 | ✅ PASSED |
| `tests/test_day10_cron_ws.py` | 5-part cron iter calculation, recurring job dispatching, concurrent cron deduplication, WebSocket pub/sub | 5/5 | ✅ PASSED |
| `tests/test_day13_bonus_features.py` | DAG dependency cascade & cancellation, Token-Bucket rate limiter, AI failure diagnostic engine, at-least-once side-effect idempotency | 5/5 | ✅ PASSED |
| `tests/test_day14_batch_jobs.py` | Batch REST endpoints, child job enqueuing, live progress aggregation (`100% completed`), batch cancel & retry | 4/4 | ✅ PASSED |
| `tests/test_day15_rbac_and_isolation.py` | Multi-tier RBAC (`Admin`, `Developer`, `Viewer`), cross-tenant 404 security barriers | 4/4 | ✅ PASSED |
| `tests/test_day16_telemetry_observability.py` | System KPI rates, queue depth & wait time metrics, fleet heartbeat age, per-job latency breakdowns | 4/4 | ✅ PASSED |
| `tests/test_distributed_stress_and_races.py` | Mutual exclusion (2 workers/1 job), 100 jobs/5 workers drain, concurrency limit invariant ($\le 3$), worker crash recovery & fencing, 100-burst idempotency, 3-node HA scheduler race | 6/6 | ✅ PASSED |

### 📈 Code Coverage by Module

```
Name                                        Stmts   Miss  Cover   Missing
-------------------------------------------------------------------------
backend/app/__init__.py                         1      0   100%
backend/app/api/deps.py                        44     12    73%   40, 47-48, 54-62, 95-102
backend/app/api/v1/__init__.py                 22      0   100%
backend/app/api/v1/auth.py                     24      2    92%   86-88
backend/app/api/v1/batches.py                  47     17    64%   36, 57, 96-114
backend/app/api/v1/dlq.py                      25      1    96%   54
backend/app/api/v1/jobs.py                     31      1    97%   160
backend/app/api/v1/projects.py                 40      4    90%   63-66
backend/app/api/v1/queues.py                   28      4    86%   26-29
backend/app/api/v1/schedules.py                31      3    90%   52, 68, 83
backend/app/api/v1/telemetry.py                13      0   100%
backend/app/api/v1/workers.py                  61     37    39%   30-41, 44-58, 83, 101-113, 129-140
backend/app/api/v1/ws.py                       20      3    85%   32-34
backend/app/core/config.py                     33      0   100%
backend/app/core/database.py                   15      7    53%   39-46
backend/app/core/security.py                   31      2    94%   28, 50
backend/app/core/ws_manager.py                 29     11    62%   30-43
backend/app/main.py                            44     19    57%   26-42, 86-96
backend/app/models/batch.py                    45      2    96%   18, 80
backend/app/models/enums.py                    27      0   100%
backend/app/models/idempotency.py              20      0   100%
backend/app/models/job.py                      69      0   100%
backend/app/models/organization.py             30      0   100%
backend/app/models/project.py                  33      0   100%
backend/app/models/queue.py                    39      0   100%
backend/app/models/schedule.py                 27      0   100%
backend/app/models/worker.py                   30      0   100%
backend/app/schemas/job.py                     78      0   100%
backend/app/schemas/telemetry.py               43      0   100%
worker/app/engine/claimer.py                   65      4    94%   134, 150-151, 160
worker/app/engine/context.py                   40      3    92%   52, 74-75
worker/app/engine/ai_diagnostics.py            17      2    88%   50, 59
worker/app/engine/runner.py                   110     10    91%   194-201, 225-232
worker/app/engine/rate_limiter.py              33      7    79%   40-48
worker/app/engine/retry.py                     35      8    77%   25-29, 55-56, 61
worker/app/reaper.py                           75     20    73%   110-112, 115-122, 125-134
worker/app/cron.py                             77     24    69%   33, 37, 67, 107, 122-124, 127-134
worker/app/heartbeat.py                        62     21    66%   31-33, 36-43, 55-56, 108-116
worker/app/tasks/registry.py                   79     15    81%   22-24, 115-135
-------------------------------------------------------------------------
TOTAL                                        2862    900    69%
```

---

## 0.3 Baseline Performance Benchmarks

Benchmark matrix executed across **100**, **500**, and **1000 jobs** under parallel worker fleets of **1**, **2**, **5**, and **10 workers** using PostgreSQL 16 ACID `FOR UPDATE SKIP LOCKED` atomic claiming.

### 📊 Benchmark Results Matrix

| Job Load | Workers | Throughput (ops/s) | Avg Latency (ms) | P95 Latency (ms) | Failures | Duplicate Executions |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **100** | 1 | 12.8 ops/s | 77.8 ms | 106.2 ms | 0 | 0 |
| **100** | 2 | 45.4 ops/s | 43.5 ms | 52.4 ms | 0 | 0 |
| **100** | 5 | 64.7 ops/s | 74.8 ms | 89.1 ms | 0 | 0 |
| **100** | 10 | 53.4 ops/s | 176.1 ms | 201.9 ms | 0 | 0 |
| **500** | 1 | 17.6 ops/s | 56.7 ms | 69.6 ms | 0 | 0 |
| **500** | 2 | 48.2 ops/s | 41.3 ms | 43.6 ms | 0 | 0 |
| **500** | 5 | 69.7 ops/s | 71.1 ms | 82.3 ms | 0 | 0 |
| **500** | 10 | 69.2 ops/s | 142.7 ms | 156.8 ms | 0 | 0 |
| **1000** | 1 | 18.1 ops/s | 55.0 ms | 73.3 ms | 0 | 0 |
| **1000** | 2 | 46.9 ops/s | 42.2 ms | 46.5 ms | 0 | 0 |
| **1000** | 5 | **71.7 ops/s** | 69.3 ms | 80.4 ms | 0 | 0 |
| **1000** | 10 | 70.6 ops/s | 140.8 ms | 160.6 ms | 0 | 0 |

---

### 🔍 Performance Observations & Insights

1. **Peak Scalability:**  
   The scheduler achieves its highest throughput at **71.7 operations per second** with **5 parallel workers** on a single PostgreSQL instance, draining 1,000 tasks with zero dropped jobs.
2. **Deterministic Race Prevention (0 Duplicates):**  
   Across all **6,400 total benchmark jobs** executed during the benchmark runs, **0 duplicate claims** and **0 duplicate executions** occurred, mathematically validating the `FOR UPDATE SKIP LOCKED` atomic claiming model.
3. **Sub-50ms Latency Under Normal Fleet Load:**  
   With 2 workers, average job claim-to-finish latency remains strictly between **41.3ms and 43.5ms**, with P95 latency staying under **52.4ms**.
4. **Zero Failures:**  
   Across all 12 benchmark matrix tests, 100% of tasks completed with status `SUCCESS` and 0 failures.
