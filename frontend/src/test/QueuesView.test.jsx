import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import QueuesView from '../components/QueuesView';
import { apiClient } from '../api/client';

vi.mock('../api/client', () => ({
  apiClient: {
    createQueue: vi.fn(),
    pauseQueue: vi.fn(),
    resumeQueue: vi.fn(),
  },
}));

describe('QueuesView Component', () => {
  const mockQueues = [
    {
      id: 'q-1',
      name: 'high-priority-queue',
      priority: 90,
      concurrency_limit: 10,
      is_paused: false,
      retry_policy: { strategy: 'exponential', backoff_multiplier: 2.0 },
    },
    {
      id: 'q-2',
      name: 'reports-batch-queue',
      priority: 20,
      concurrency_limit: 3,
      is_paused: true,
      retry_policy: { strategy: 'linear', backoff_multiplier: 1.0 },
    },
  ];

  it('renders queue cards with status, concurrency limits, and pause/resume buttons', () => {
    const onRefresh = vi.fn();

    render(
      <QueuesView
        queues={mockQueues}
        selectedProject={{ id: 'p-1', name: 'Production Project' }}
        onRefresh={onRefresh}
      />
    );

    expect(screen.getByText('high-priority-queue')).toBeInTheDocument();
    expect(screen.getByText('reports-batch-queue')).toBeInTheDocument();

    expect(screen.getByText('ACTIVE')).toBeInTheDocument();
    expect(screen.getByText('PAUSED')).toBeInTheDocument();

    // Check pause / resume buttons
    const pauseBtns = screen.getAllByRole('button', { name: /Pause/i });
    expect(pauseBtns.length).toBeGreaterThan(0);
  });

  it('calls pauseQueue when Pause button is clicked on an active queue', async () => {
    const onRefresh = vi.fn();
    apiClient.pauseQueue.mockResolvedValue({ data: { success: true } });

    render(
      <QueuesView
        queues={mockQueues}
        selectedProject={{ id: 'p-1', name: 'Production Project' }}
        onRefresh={onRefresh}
      />
    );

    const pauseBtn = screen.getByRole('button', { name: /Pause Queue/i });
    fireEvent.click(pauseBtn);

    expect(apiClient.pauseQueue).toHaveBeenCalledWith('q-1');
  });
});
