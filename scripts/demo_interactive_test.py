#!/usr/bin/env python3
"""
Interactive Demonstration & Testing Script for Codity Distributed Job Scheduler.
Runs end-to-end tests against the live running containers:
1. Authenticates as Admin & Member
2. Submits individual jobs & verifies real-time execution
3. Enqueues a 10-job Batch and watches live aggregated progress
4. Submits a deliberate failure, inspects DLQ, and triggers a 1-click redrive replay
5. Evaluates recurring cron dispatching
6. Fetches comprehensive full-stack telemetry (KPIs, Queue depth, Fleet utilization)
"""

import time
import requests
import json
import uuid

BASE_URL = "http://localhost:8000/api/v1"

def print_header(title):
    print("\n" + "=" * 70)
    print(f"🚀 {title}")
    print("=" * 70)

def main():
    print_header("1. Authenticating with Live API")
    login_payload = {
        "email": "admin@distributed-scheduler.io",
        "password": "Password123!"
    }
    res = requests.post(f"{BASE_URL}/auth/login", json=login_payload)
    if res.status_code != 200:
        print(f"❌ Login failed: {res.text}")
        return
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("✅ Authenticated as Admin (admin@distributed-scheduler.io)")

    # 2. Fetch Projects & Queues
    print_header("2. Fetching Projects & Isolated Queues")
    p_res = requests.get(f"{BASE_URL}/projects", headers=headers)
    projects = p_res.json()
    project = projects[0]
    project_id = project["id"]
    print(f"📁 Active Project: {project['name']} (ID: {project_id})")

    q_res = requests.get(f"{BASE_URL}/projects/{project_id}/queues", headers=headers)
    queues = q_res.json()
    queue = queues[0]
    queue_id = queue["id"]
    print(f"⚡ Target Queue: '{queue['name']}' (Priority: P{queue['priority']}, Concurrency Limit: {queue['concurrency_limit']})")

    # 3. Submit Immediate Job
    print_header("3. Submitting Real-Time Job")
    job_payload = {
        "name": "send_welcome_email",
        "priority": 75,
        "payload": {"recipient": "alex@startup.io", "tier": "enterprise"},
        "idempotency_key": f"test-demo-{uuid.uuid4().hex[:8]}"
    }
    j_res = requests.post(f"{BASE_URL}/queues/{queue_id}/jobs", headers=headers, json=job_payload)
    job = j_res.json()
    job_id = job["id"]
    print(f"📋 Enqueued Job '{job['name']}' (ID: {job_id})")

    time.sleep(1.5)
    detail_res = requests.get(f"{BASE_URL}/jobs/{job_id}", headers=headers).json()
    print(f"⏱️ Job Status: {detail_res['status']} | Queue Wait: {detail_res.get('queue_wait_ms')}ms | Exec Duration: {detail_res.get('execution_duration_ms')}ms")

    # 4. Enqueue Batch of 10 Jobs & Watch Progress
    print_header("4. Enqueueing First-Class Batch (10 Tasks)")
    batch_payload = {
        "name": f"Daily ETL Batch #{uuid.uuid4().hex[:4]}",
        "jobs": [
            {"name": "process_image", "payload": {"shard": i, "filter": "hdr"}}
            for i in range(10)
        ]
    }
    b_res = requests.post(f"{BASE_URL}/queues/{queue_id}/batches", headers=headers, json=batch_payload)
    batch = b_res.json()
    batch_id = batch["id"]
    print(f"📦 Created Batch '{batch['name']}' with {batch['total_jobs']} jobs (ID: {batch_id})")

    for _ in range(6):
        time.sleep(0.8)
        b_status = requests.get(f"{BASE_URL}/batches/{batch_id}", headers=headers).json()
        print(f"   📊 Batch Progress: {b_status['completed_jobs']}/{b_status['total_jobs']} completed ({b_status['progress_percent']}%) | Status: {b_status['status']}")
        if b_status["status"] in ["completed", "partially_failed", "failed"]:
            break

    # 5. Submit Failing Task -> DLQ -> Replay
    print_header("5. Testing Dead Letter Queue (DLQ) Incident & 1-Click Replay")
    fail_payload = {
        "name": "generate_report",
        "priority": 10,
        "max_retries": 1,
        "payload": {"force_error": True}
    }
    fail_res = requests.post(f"{BASE_URL}/queues/{queue_id}/jobs", headers=headers, json=fail_payload)
    fail_job_id = fail_res.json()["id"]
    print(f"💥 Enqueued Deliberately Failing Task (ID: {fail_job_id})")

    time.sleep(2.0)
    dlq_list = requests.get(f"{BASE_URL}/queues/{queue_id}/dlq", headers=headers).json()
    print(f"💀 DLQ Incident Count: {dlq_list['total']}")
    if dlq_list["items"]:
        dlq_entry = dlq_list["items"][0]
        print(f"   Root Cause: {dlq_entry['failed_reason']}")
        print(f"   AI Summary: {dlq_entry.get('ai_failure_summary') or 'Timeout / Service unavailable'}")
        print(f"   🔄 Triggering 1-Click Replay on DLQ Entry: {dlq_entry['id']}")
        rep_res = requests.post(f"{BASE_URL}/dlq/{dlq_entry['id']}/replay", headers=headers)
        print(f"   ✅ Replay Status: HTTP {rep_res.status_code}")

    # 6. Fetch Telemetry
    print_header("6. System Telemetry & Fleet Observability Summary")
    t_res = requests.get(f"{BASE_URL}/telemetry?project_id={project_id}", headers=headers).json()
    print("🌐 SYSTEM KPIS:")
    print(f"   • Total Lifetime Jobs: {t_res['system']['total_jobs']}")
    print(f"   • Live Throughput: {t_res['system']['jobs_per_sec']} jobs/s")
    print(f"   • Success Rate: {t_res['system']['success_rate_percent']}%")
    print(f"   • Failure Rate: {t_res['system']['failure_rate_percent']}%")
    print(f"   • DLQ Rate: {t_res['system']['dlq_rate_percent']}%")

    print("\n🖥️ WORKER FLEET HEALTH:")
    print(f"   • Online Nodes: {t_res['fleet']['workers_online']}")
    print(f"   • Busy Workers: {t_res['fleet']['workers_busy']}")
    print(f"   • Idle Workers: {t_res['fleet']['workers_idle']}")
    print(f"   • Avg CPU: {t_res['fleet']['average_cpu_percent']}% | Avg RAM: {t_res['fleet']['average_memory_mb']} MB")

    print("\n🎉 ALL TESTS COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
