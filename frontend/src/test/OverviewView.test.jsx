import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import OverviewView from '../components/OverviewView';
import { apiClient } from '../api/client';

vi.mock('../api/client', () => ({
  apiClient: {
    getTelemetry: vi.fn(),
  },
}));

describe('OverviewView Component', () => {
  const mockQueues = [
    { id: 'q-1', name: 'critical-queue', is_paused: false, concurrency_limit: 10 },
    { id: 'q-2', name: 'background-queue', is_paused: true, concurrency_limit: 5 },
  ];

  const mockJobs = {
    total: 10,
    items: [
      { id: 'job-1', name: 'sync_orders', status: 'completed', duration_ms: 120 },
      { id: 'job-2', name: 'render_thumbnail', status: 'running' },
      { id: 'job-3', name: 'send_sms', status: 'queued' },
    ],
  };

  const mockWorkers = [
    { id: 'worker-1', is_alive: true, current_active_jobs: 1, max_concurrency: 5, cpu_percent: 14.5, memory_mb: 256.0 },
    { id: 'worker-2', is_alive: true, current_active_jobs: 0, max_concurrency: 5, cpu_percent: 8.2, memory_mb: 180.0 },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    apiClient.getTelemetry.mockResolvedValue({
      data: {
        system: {
          total_jobs: 10,
          jobs_per_sec: 2.5,
          success_rate_percent: 98.5,
          failure_rate_percent: 1.5,
          retry_rate_percent: 3.0,
          dlq_rate_percent: 0.5,
        },
        fleet: {
          workers_online: 2,
          workers_busy: 1,
          workers_idle: 1,
          average_cpu_percent: 11.3,
          average_memory_mb: 218.0,
        },
        queues: [],
      },
    });
  });

  it('renders KPI metric cards and summary telemetry', () => {
    const onInspectJob = vi.fn();

    render(
      <OverviewView
        queues={mockQueues}
        jobs={mockJobs}
        workers={mockWorkers}
        dlqCount={1}
        selectedProject={{ id: 'p-1', name: 'Primary Project' }}
        onInspectJob={onInspectJob}
      />
    );

    // KPI labels
    expect(screen.getByText('Total Jobs')).toBeInTheDocument();
    expect(screen.getAllByText('Throughput').length).toBeGreaterThan(0);
    expect(screen.getByText('Success Rate')).toBeInTheDocument();
    expect(screen.getByText('Failure Rate')).toBeInTheDocument();
    expect(screen.getByText('Retry Rate')).toBeInTheDocument();
    expect(screen.getByText('DLQ Rate')).toBeInTheDocument();

    // Fleet summary
    expect(screen.getByText('Worker Fleet:')).toBeInTheDocument();
    expect(screen.getByText('2 Online')).toBeInTheDocument();
  });
});
