import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import SchedulesView from '../components/SchedulesView';
import { apiClient } from '../api/client';

vi.mock('../api/client', () => ({
  apiClient: {
    getSchedules: vi.fn(),
    createSchedule: vi.fn(),
    pauseSchedule: vi.fn(),
    resumeSchedule: vi.fn(),
    deleteSchedule: vi.fn(),
  },
}));

describe('SchedulesView Component', () => {
  const mockQueues = [{ id: 'q-1', name: 'cron-queue' }];
  const mockSchedules = [
    {
      id: 'sched-1',
      name: 'Nightly Database Backup',
      cron_expression: '0 0 * * *',
      is_active: true,
      queue_id: 'q-1',
      priority: 50,
      next_run_at: '2026-08-25T00:00:00Z',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    apiClient.getSchedules.mockResolvedValue({ data: mockSchedules });
  });

  it('renders recurring cron schedules with expression and status', async () => {
    render(
      <SchedulesView
        queues={mockQueues}
        selectedQueueId="q-1"
        selectedProject={{ id: 'p-1', name: 'Main Project' }}
        onRefresh={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Nightly Database Backup')).toBeInTheDocument();
    });

    expect(screen.getByText('0 0 * * *')).toBeInTheDocument();
    expect(screen.getByText('ACTIVE CRON')).toBeInTheDocument();
  });
});
