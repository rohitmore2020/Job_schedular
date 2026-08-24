import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import JobsView from '../components/JobsView';

describe('JobsView Component', () => {
  const mockQueues = [
    { id: 'q-1', name: 'critical-queue' },
    { id: 'q-2', name: 'background-queue' },
  ];

  const mockJobs = {
    total: 3,
    items: [
      {
        id: 'job-aaa-111',
        name: 'sync_user_stripe_account',
        status: 'completed',
        priority: 80,
        attempt_count: 1,
        max_retries: 3,
        queue_id: 'q-1',
        run_at: '2026-08-24T10:00:00Z',
        created_at: '2026-08-24T09:59:50Z',
      },
      {
        id: 'job-bbb-222',
        name: 'generate_analytics_report',
        status: 'running',
        priority: 50,
        attempt_count: 1,
        max_retries: 3,
        queue_id: 'q-1',
        run_at: '2026-08-24T10:05:00Z',
        created_at: '2026-08-24T10:04:55Z',
      },
      {
        id: 'job-ccc-333',
        name: 'send_welcome_email',
        status: 'queued',
        priority: 10,
        attempt_count: 0,
        max_retries: 2,
        queue_id: 'q-2',
        run_at: '2026-08-24T10:10:00Z',
        created_at: '2026-08-24T10:09:58Z',
      },
    ],
  };

  it('renders list of jobs with names, status badges, and priorities', () => {
    const onInspectJob = vi.fn();

    render(
      <JobsView
        jobs={mockJobs}
        queues={mockQueues}
        selectedQueueId={null}
        setSelectedQueueId={vi.fn()}
        onInspectJob={onInspectJob}
        onRefresh={vi.fn()}
      />
    );

    expect(screen.getByText('sync_user_stripe_account')).toBeInTheDocument();
    expect(screen.getByText('generate_analytics_report')).toBeInTheDocument();
    expect(screen.getByText('send_welcome_email')).toBeInTheDocument();

    expect(screen.getByText('completed')).toBeInTheDocument();
    expect(screen.getByText('running')).toBeInTheDocument();
    expect(screen.getByText('queued')).toBeInTheDocument();
  });

  it('triggers onInspectJob drawer when a job Inspect button is clicked', () => {
    const onInspectJob = vi.fn();

    render(
      <JobsView
        jobs={mockJobs}
        queues={mockQueues}
        selectedQueueId={null}
        setSelectedQueueId={vi.fn()}
        onInspectJob={onInspectJob}
        onRefresh={vi.fn()}
      />
    );

    const inspectBtns = screen.getAllByRole('button', { name: /Inspect/i });
    fireEvent.click(inspectBtns[0]);

    expect(onInspectJob).toHaveBeenCalledWith('job-aaa-111');
  });
});
