import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import WorkersView from '../components/WorkersView';
import { apiClient } from '../api/client';

vi.mock('../api/client', () => ({
  apiClient: {
    getWorkerHeartbeats: vi.fn(),
  },
}));

describe('WorkersView Component', () => {
  const mockWorkers = [
    {
      id: 'worker-1',
      worker_id: 'worker-node-alpha',
      hostname: 'scheduler-node-1',
      pid: 1042,
      is_alive: true,
      concurrency_limit: 10,
      current_active_jobs: 3,
      jobs_processed: 450,
      failure_count: 2,
      heartbeat_age_seconds: 2,
    },
    {
      id: 'worker-2',
      worker_id: 'worker-node-beta',
      hostname: 'scheduler-node-2',
      pid: 1043,
      is_alive: false,
      concurrency_limit: 10,
      current_active_jobs: 0,
      jobs_processed: 120,
      failure_count: 10,
      heartbeat_age_seconds: 180,
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    apiClient.getWorkerHeartbeats.mockResolvedValue({
      data: [
        { timestamp: '2026-08-24T12:00:00Z', cpu_percent: 15.2, memory_mb: 210.5, active_jobs: 3 },
      ],
    });
  });

  it('renders worker cards with heartbeat metrics and health badges', () => {
    const onRefresh = vi.fn();

    render(
      <WorkersView
        workers={mockWorkers}
        onRefresh={onRefresh}
      />
    );

    expect(screen.getAllByText('worker-node-alpha').length).toBeGreaterThan(0);
    expect(screen.getByText('worker-node-beta')).toBeInTheDocument();

    expect(screen.getByText('BUSY')).toBeInTheDocument();
    expect(screen.getByText('DEAD')).toBeInTheDocument();

    expect(screen.getByText('Workers Online')).toBeInTheDocument();
    expect(screen.getByText('Workers Busy')).toBeInTheDocument();
  });
});
